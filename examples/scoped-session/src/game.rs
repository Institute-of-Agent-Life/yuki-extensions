use crate::rpc::Result;
use serde_json::{Value, json};

const INSTRUCTIONS: &str = "\
Run a short lighthouse rescue game. A boat is approaching a reef in thick fog. \
The lamp has no lens, and the player starts with an empty inventory. \
The lens is in a crate in the storeroom. Searching finds the lens, fitting it aligns the lamp, \
and signalling with the aligned lamp guides the boat to safety. \
Remember the player's inventory and the lamp state across turns. \
Let the player attempt the moves in order and explain what is missing if they try a move too early. \
Narrate the effect of the current move in at most 80 words. Stay inside the game.";

pub fn request(command: &Value) -> Result<(&'static str, Value)> {
    if command["name"] != "/lighthouse" {
        return Err("unknown_command".into());
    }
    let handle = command["handle"]
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or("original_handle_required")?;
    let operation = command["operation"]
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or("original_operation_required")?;
    let text = command["arguments"]["text"]
        .as_str()
        .ok_or("command_text_required")?;
    let mut words = text.split_whitespace();
    let name = words.next();
    let authority = json!({"handle":handle});
    match name {
        Some("/lighthouse/start") if words.next().is_none() => Ok((
            "session.create",
            json!({"key":operation,"authority":authority,"name":"The lighthouse",
                   "instructions":INSTRUCTIONS,"route":"game","purpose":"game",
                   "persistence":"durable","context_profile":"none"}),
        )),
        Some("/lighthouse/status") => {
            let session = words.next().ok_or("session_required")?;
            let after = words
                .next()
                .map_or(Ok(0), str::parse::<u64>)
                .map_err(|_| "invalid_offset")?;
            if words.next().is_some() {
                return Err("invalid_status_arguments".into());
            }
            Ok((
                "session.page",
                json!({"session":session,"authority":authority,"after":after}),
            ))
        }
        Some("/lighthouse/play") => {
            let session = words.next().ok_or("session_required")?;
            let epoch = words
                .next()
                .and_then(|v| v.parse::<u64>().ok())
                .ok_or("epoch_required")?;
            let key = words.next().ok_or("turn_key_required")?;
            if key.len() > 128
                || !key
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
            {
                return Err("invalid_turn_key".into());
            }
            let action = match (words.next(), words.next()) {
                (Some("search"), None) => "Search the storeroom for the missing lens.",
                (Some("fit"), None) => "Fit the lens and align the lamp.",
                (Some("signal"), None) => "Signal the boat with the lighthouse lamp.",
                _ => return Err("choose_search_fit_or_signal".into()),
            };
            Ok((
                "session.run",
                json!({"session":session,"authority":authority,
                                     "key":key,"epoch":epoch,"user_input":action}),
            ))
        }
        _ => Err("choose_start_status_or_play".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn command(text: &str) -> Value {
        json!({"name":"/lighthouse","operation":"command:9","handle":"original","arguments":{"text":text}})
    }

    #[test]
    fn starts_durable_game_under_original_invocation() {
        let (method, args) = request(&command("/lighthouse/start")).unwrap();
        assert_eq!(method, "session.create");
        assert_eq!(args["authority"]["handle"], "original");
        assert_eq!(args["key"], "command:9");
        assert_eq!(args["context_profile"], "none");
        assert_eq!(args["persistence"], "durable");
    }

    #[test]
    fn stable_move_key_and_epoch_are_explicit() {
        let (method, args) = request(&command("/lighthouse/play session 2 turn-3 fit")).unwrap();
        assert_eq!(method, "session.run");
        assert_eq!(args["key"], "turn-3");
        assert_eq!(args["epoch"], 2);
        assert_eq!(args["user_input"], "Fit the lens and align the lamp.");
    }

    #[test]
    fn rejects_unbound_calls_or_invalid_actions() {
        assert!(request(&command("/lighthouse/play session 0 turn escape")).is_err());
        assert!(request(&command("/lighthouse/play session 0 invalid/key search")).is_err());
        assert!(request(&command("/lighthouse/status session -1")).is_err());
        let mut forged = command("/lighthouse/start");
        forged["handle"] = Value::Null;
        assert!(request(&forged).is_err());
    }
}
