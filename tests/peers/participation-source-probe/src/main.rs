mod rpc;
use serde_json::{json,Value};
use std::{io,sync::{Arc,atomic::AtomicBool},thread};
use yuki_plugin_sdk::{read_frame,host::Incoming};
use base64::{Engine,engine::general_purpose::STANDARD};
fn main()->Result<(),Box<dyn std::error::Error>>{
 let mut input=io::stdin().lock();let rpc=Arc::new(rpc::handshake(&mut input)?);
 while let Some(raw)=read_frame(&mut input)?{
  let frame=rpc.calls.lock().unwrap().receive(&raw)?;
  match frame{
   Incoming::Result{id,result,..}=>{if let Some(tx)=rpc.pending.lock().unwrap().remove(&id){let _=tx.send(result.map_err(|x|x.to_string()));}},
   Incoming::Notification{method,params} if method=="observer.event"=>{let rpc=rpc.clone();thread::spawn(move||{
    let event=params["event"].clone();let cancel=AtomicBool::new(false);let mut result=json!({"notification":params});
    let mut bytes=vec![];let mut version=Value::Null;
    loop{
     let mut request=json!({"event":event,"cursor":bytes.len()});if !version.is_null(){request["version"]=version.clone();}
     match rpc.call("participation.source",request,&cancel){
      Ok(page)=>{version=page["version"].clone();bytes.extend(STANDARD.decode(page["data"].as_str().unwrap()).unwrap());if page["complete"]==true{result["source"]=serde_json::from_slice(&bytes).unwrap();result["version"]=version;break;}},
      Err(e)=>{result["error"]=json!(e);break;}
     }
    }
    let path=std::path::PathBuf::from(std::env::var("YUKI_PARTICIPATION_PROBE").unwrap()).join(format!("source-{event}.json"));std::fs::write(path,serde_json::to_vec_pretty(&result).unwrap()).unwrap();
   });},
   Incoming::Call{method,id,params} if method=="forget.request"=>{let _=params;let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"diagnostic_probe_does_not_ack_erasure"}}));},
   _=>()
  }
 }Ok(())
}
