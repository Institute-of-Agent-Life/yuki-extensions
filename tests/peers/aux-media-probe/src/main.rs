mod rpc;
use serde_json::json;
use std::{io,sync::{Arc,atomic::AtomicBool},thread};
use yuki_plugin_sdk::{host::Incoming,read_frame};
fn main()->Result<(),Box<dyn std::error::Error>> {
 let mut input=io::stdin().lock();let rpc=Arc::new(rpc::handshake(&mut input)?);
 while let Some(raw)=read_frame(&mut input)? {
  let m=rpc.calls.lock().unwrap().receive(&raw)?;
  match m {
   Incoming::Result{id,result,..}=>{if let Some(tx)=rpc.pending.lock().unwrap().remove(&id){let _=tx.send(result.map_err(|e|format!("{e:?}")));}},
   Incoming::Call{method,id,params} if method=="media.process"=>{
    let r=rpc.clone();thread::spawn(move||{
     let cancel=AtomicBool::new(false);let h=&params["handle"];
     let mut results=vec![];
     results.push(json!({"open":r.call("media.open",json!({"handle":h,"offset":0,"length":1}),&cancel)}));
     for selected in [false,true] {
      let v=r.call("llm.complete",json!({"origin":{"handle":h},"route":"asr","purpose":"transcript","call_id":format!("diagnostic-{selected}"),"text":"transcribe","selected_media":selected}),&cancel);
      results.push(json!({"selected_media":selected,"result":v}));
     }
     r.reply(id,json!({"ok":true,"data":{"diagnostic_only":true,"calls":results}}));
    });
   },
   Incoming::Call{id,..}=>{let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"diagnostic method unavailable"}}));},
   _=>()
  }
 }
 Ok(())
}
