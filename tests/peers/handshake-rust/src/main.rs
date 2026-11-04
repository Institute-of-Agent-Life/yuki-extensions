use std::io::{self, Write};
use yuki_plugin_sdk::{Binding, Id, Peer, Received, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let binding_file = std::env::args_os().nth(1).ok_or("missing binding")?;
    let binding: Binding = serde_json::from_slice(&std::fs::read(binding_file)?)?;
    let mut offer = binding.offer();
    offer.optional_features.push("ext002.optional".into());
    let mut peer = Peer::new(binding)?;
    let mut out = io::stdout().lock();
    writeln!(out, "{}", peer.request(Id::Number(1), offer)?)?;
    out.flush()?;

    let mut input = io::stdin().lock();
    while let Some(frame) = read_frame(&mut input)? {
        match peer.receive(&frame)? {
            Received::Reply(frame) => {
                writeln!(out, "{frame}")?;
                out.flush()?;
            }
            Received::Response { id, result } => {
                let accepted = result.map_err(|error| error.to_string())?;
                eprintln!("{}", serde_json::json!({"id": id, "accepted": accepted}));
            }
            Received::Notification => {}
        }
    }
    peer.finish()?;
    Ok(())
}
