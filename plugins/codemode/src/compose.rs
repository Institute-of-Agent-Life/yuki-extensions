use crate::{catalog, rpc::{Rpc,Result}, worker::{Worker,field,digest,same_contract}};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value,json};
use std::sync::atomic::AtomicBool;
const MAX_SNAPSHOT: usize = 8 * 1024 * 1024;
fn number(v:&Value,key:&str)->Result<u64>{v[key].as_u64().ok_or_else(||format!("missing_{key}"))}
fn upload(rpc:&Rpc,handle:&str,state:&Value,cancel:&AtomicBool)->Result<String>{
 let bytes=serde_json::to_vec(state).map_err(|_|"snapshot_invalid")?;
 if bytes.is_empty() || bytes.len()>MAX_SNAPSHOT{return Err("snapshot_limit".into());}
 let sha=digest(&bytes);
 for (index,chunk) in bytes.chunks(16384).enumerate(){
  let offset=index*16384;
  let r=rpc.call("code.snapshot.put",json!({"handle":handle,"snapshot":sha,"sha256":sha,"size":bytes.len(),"codec":state["contract"]["codec_sha256"],"offset":offset,"bytes":STANDARD.encode(chunk)}),cancel)?;
  if number(&r,"next_offset")? != (offset+chunk.len()) as u64{return Err("snapshot_upload_offset".into());}
 }
 Ok(sha)
}
fn download(rpc:&Rpc,handle:&str,snapshot:&str,cancel:&AtomicBool)->Result<Value>{
 let mut bytes=vec![];let mut expected=None;
 loop{
  let page=rpc.call("code.snapshot.get",json!({"handle":handle,"snapshot":snapshot,"offset":bytes.len()}),cancel)?;
  let size=number(&page,"size")? as usize;let sha=field(&page,"sha256")?.to_owned();
  if size==0 || size>MAX_SNAPSHOT{return Err("snapshot_limit".into());}
  if let Some(prior)=&expected{if prior!=&(size,sha.clone()){return Err("snapshot_changed".into());}}
  expected=Some((size,sha.clone()));
  let chunk=STANDARD.decode(field(&page,"bytes")?).map_err(|_|"snapshot_bytes_invalid")?;
  if chunk.is_empty()||bytes.len()+chunk.len()>size{return Err("snapshot_page_invalid".into());}
  bytes.extend(chunk);
  if bytes.len()==size{
   if digest(&bytes)!=sha{return Err("snapshot_digest_mismatch".into());}
   return serde_json::from_slice(&bytes).map_err(|_|"snapshot_unavailable".into());
  }
 }
}
fn native_restore(state:&Value)->Result<Value>{
 let native=&state["native"];
 let mut request=json!({"op":"restore","manifest":manifest(state)?});
 for key in ["snapshot","snapshot_sha256","saved","counters"]{
  request[key]=native.get(key).ok_or("snapshot_unavailable")?.clone();
 }
 Ok(request)
}
fn manifest(state:&Value)->Result<Vec<String>>{
 Ok(state["projection"].as_object().ok_or("snapshot_projection_invalid")?.keys().cloned().collect())
}
fn execute(rpc:&Rpc,params:&Value,resume:bool,worker:&mut Worker,cancel:&AtomicBool)->Result<Value>{
 let handle=field(params,"handle")?; let operation=field(params,"operation")?;
 // Refresh current source authority before retaining any native private content.
 rpc.call("code.sources",json!({"handle":handle,"limit":1}),cancel)?;
 let mut checkpoint=if resume{number(params,"checkpoint")?}else{0};
 let children=params["children"].as_array().cloned().unwrap_or_default();
 let mut state=if resume{
  let value=download(rpc,handle,field(params,"snapshot")?,cancel)?;
  if value["format"]!=1||value["operation"]!=operation||!same_contract(&value["contract"],&worker.contract)||!same_contract(&params["contract"],&worker.contract){return Err("snapshot_unavailable".into());}
  if value["native"]["outcome"]["status"]=="suspended"{
   let restored=worker.exchange(&native_restore(&value)?,cancel)?;
   if restored["outcome"]["call"]!=value["native"]["outcome"]["call"]||restored["outcome"]["status"]!="suspended"{return Err("snapshot_unavailable".into());}
   let mut value=value;value["native"]=restored;value
  }else{value}
 }else{
  let code=field(&params["arguments"],"code")?;
  let projection=catalog::projection(rpc,handle,cancel)?;
  let mut value=json!({"format":1,"operation":operation,"revision":params["revision"],"next":0,"contract":worker.contract,"projection":projection});
  value["native"]=worker.exchange(&json!({"op":"start","manifest":manifest(&value)?,"code":code,"inputs":{}}),cancel)?;value
 };
 loop{
  let native=&state["native"];
  match native["outcome"]["status"].as_str(){
   Some("completed")=>return Ok(json!({"status":"completed","children":state["next"],"outcome":native["outcome"],"counters":native["counters"]})),
   Some("failed")=>return Ok(json!({"status":"failed","children":state["next"],"outcome":native["outcome"],"counters":native["counters"]})),
   Some("suspended")=>(),_=>return Err("native_outcome_invalid".into())
  }
  let call=native["outcome"]["call"].clone();
  if call["kind"]!="function"{return Err("native_future_unavailable".into());}
  let ordinal=number(&state,"next")?;
  let feed=number(&call,"feed_index")?;let call_id=number(&call,"engine_call_id")?;
  let name=field(&state["projection"],field(&call,"function_name")?)?;
  let args=call["args"].as_array().ok_or("native_arguments_invalid")?;
  if args.len()!=1||!args[0].is_object()||call["kwargs"].as_object().is_none_or(|m|!m.is_empty()){return Err("script_requires_one_object".into());}
  let child=if let Some(old)=children.iter().find(|x|x["ordinal"]==ordinal){
   if old["feed_index"]!=feed||old["engine_call_id"]!=call_id.to_string(){return Err("snapshot_child_mismatch".into());}
   rpc.call("tool.resume",json!({"handle":handle,"ordinal":ordinal,"feed_index":feed,"engine_call_id":call_id.to_string()}),cancel)?
  }else{
   let snapshot=upload(rpc,handle,&state,cancel)?;
   rpc.call("tool.invoke",json!({"handle":handle,"checkpoint":checkpoint,"ordinal":ordinal,"feed_index":feed,"engine_call_id":call_id.to_string(),"snapshot":snapshot,"name":name,"arguments":args[0]}),cancel)?
  };
  if child["can_feed"]!=true{return Ok(json!({"status":"partial","observed":child}));}
  if child["feed_index"]!=feed||child["engine_call_id"]!=call_id.to_string(){return Err("receipt_position_mismatch".into());}
  state["native"]=worker.exchange(&json!({"op":"answer","engine_call_id":call_id,"answer":{"kind":"value","value":child["receipt"]}}),cancel)?;
  state["next"]=json!(ordinal+1);
  let after=upload(rpc,handle,&state,cancel)?;
  // Native feed_index indexes submitted program feeds, not host answers. Two
  // sequential calls in one feed retain index 0 and distinct engine call IDs.
  let after_feed=number(&state["native"]["counters"],"feeds")?.checked_sub(1).ok_or("native_feed_invalid")?;
  let ack=rpc.call("tool.resume",json!({"handle":handle,"ordinal":ordinal,"feed_index":feed,"engine_call_id":call_id.to_string(),"ack":{"checkpoint":child["checkpoint"],"snapshot":after,"feed_index":after_feed}}),cancel)?;
  checkpoint=number(&ack,"checkpoint")?;
 }
}
pub fn process(rpc:&Rpc,params:&Value,resume:bool,cancel:&AtomicBool)->Result<Value>{
 let mut worker=Worker::start(cancel)?;
 let result=execute(rpc,params,resume,&mut worker,cancel);
 if !worker.close(){return Err("temporary_cleanup_failed".into());}
 result
}
