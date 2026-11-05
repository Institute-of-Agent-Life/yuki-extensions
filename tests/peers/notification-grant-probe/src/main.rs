mod rpc;
use serde_json::json;
use std::{io,sync::{Arc,atomic::{AtomicBool,Ordering}},thread};
use yuki_plugin_sdk::{read_frame,host::Incoming};
fn main()->Result<(),Box<dyn std::error::Error>>{
 let mut input=io::stdin().lock();let rpc=Arc::new(rpc::handshake(&mut input)?);
 let stop=Arc::new(AtomicBool::new(false));let mut workers=vec![];
 let result:Result<(),String>=loop{
  let raw=match read_frame(&mut input){Ok(Some(v))=>v,Ok(None)=>break Ok(()),Err(e)=>break Err(e.to_string())};
  let incoming=match rpc.calls.lock().unwrap().receive(&raw){Ok(v)=>v,Err(e)=>break Err(e.to_string())};
  match incoming{
   Incoming::Result{id,result,..}=>{if let Some(tx)=rpc.pending.lock().unwrap().remove(&id){let _=tx.send(result.map_err(|e|e.to_string()));}}
   Incoming::Call{method,id,params} if method=="tool.call"=>{
    let(r,s)=(rpc.clone(),stop.clone());workers.push(thread::spawn(move||{
     let status=r.call("tool.status",json!({"handle":params["handle"]}),&s);
     let mut request=json!({"handle":params["handle"],"key":format!("probe:{}",params["operation"].as_str().unwrap_or("")),"target":params["arguments"]["target"]});
     if params["arguments"]["bot_user_id"].is_string(){request["bot_user_id"]=params["arguments"]["bot_user_id"].clone();}
     let response=r.call("notification.grant_target",request.clone(),&s);
     r.reply(id,json!({"ok":true,"data":{"original_call":params,"status":status,"request":request,"response":response}}));
    }));
   }
   Incoming::Call{id,..}=>{let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"diagnostic tool only"}}));}
   Incoming::Notification{..}=>()
  }
 };
 stop.store(true,Ordering::Release);for w in workers{let _=w.join();}result?;Ok(())
}
