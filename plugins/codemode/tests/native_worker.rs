use serde_json::json;
use std::sync::atomic::{AtomicBool,Ordering};
use yuki_codemode::worker::Worker;

#[test]
fn cancelled_admission_starts_no_worker(){
 let cancel=AtomicBool::new(true);
 let error=Worker::start(&cancel).err().expect("cancelled admission cannot start");
 assert!(error=="cancelled"||error=="runtime_abi_unavailable");
}

// Opt in only on a real Linux host with the pinned image and enforced policies.
#[test]
#[ignore = "requires the installed native runtime and enforced AppArmor/seccomp"]
fn native_suspend_restore_and_cancel(){
 assert!(cfg!(target_os="linux"));
 let cancel=AtomicBool::new(false);
 let mut first=Worker::start(&cancel).unwrap();
 let before=first.exchange(&json!({"op":"start","manifest":["yuki_echo"],"code":"a = yuki_echo({'x':1})\nb = yuki_echo({'x':1})\n[a,b]"}),&cancel).unwrap();
 assert_eq!(before["outcome"]["status"],"suspended");
 let call=before["outcome"]["call"].clone();
 assert!(first.close());
 let mut second=Worker::start(&cancel).unwrap();
 let mut restore=json!({"op":"restore","manifest":["yuki_echo"]});
 for key in ["snapshot","snapshot_sha256","saved","counters"]{restore[key]=before[key].clone();}
 let restored=second.exchange(&restore,&cancel).unwrap();
 assert_eq!(restored["outcome"]["call"],call);
 let after=second.exchange(&json!({"op":"answer","engine_call_id":call["engine_call_id"],"answer":{"kind":"value","value":"first"}}),&cancel).unwrap();
 assert_eq!(after["outcome"]["status"],"suspended");
 assert_eq!(call["feed_index"],after["outcome"]["call"]["feed_index"]);
 assert_ne!(call["engine_call_id"],after["outcome"]["call"]["engine_call_id"]);
 let done=second.exchange(&json!({"op":"answer","engine_call_id":after["outcome"]["call"]["engine_call_id"],"answer":{"kind":"value","value":"second"}}),&cancel).unwrap();
 assert_eq!(done["outcome"]["output"],json!(["first","second"]));
 assert!(second.close());
 let mut third=Worker::start(&cancel).unwrap();
 cancel.store(true,Ordering::Release);
 assert_eq!(third.exchange(&json!({"op":"start","manifest":[],"code":"while True: pass"}),&cancel).unwrap_err(),"cancelled");
 assert!(third.close());
}
