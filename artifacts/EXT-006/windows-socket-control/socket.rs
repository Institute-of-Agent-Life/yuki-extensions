use std::time::{Instant,Duration};
use std::net::{TcpStream,TcpListener};
use std::io::Read;
fn main() {
 let port=TcpListener::bind("127.0.0.1:0").unwrap();
 let mut client=TcpStream::connect(port.local_addr().unwrap()).unwrap();
 let (_keep,_a)=port.accept().unwrap();
 client.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
 let timer=client.try_clone().unwrap();timer.set_read_timeout(Some(Duration::from_millis(300))).unwrap();
 println!("client_timeout={:?} duplicate_timeout={:?}",client.read_timeout().unwrap(),timer.read_timeout().unwrap());
 drop(timer);let mut b=[0];let t=Instant::now();let e=client.read(&mut b).unwrap_err();
 println!("duplicate_set -> original_read={:?} elapsed_ms={}",e.kind(),t.elapsed().as_millis());
 client.set_read_timeout(Some(Duration::from_millis(300))).unwrap();
 let t=Instant::now();let e=client.read(&mut b).unwrap_err();
 println!("direct_set -> original_read={:?} elapsed_ms={}",e.kind(),t.elapsed().as_millis());
}
