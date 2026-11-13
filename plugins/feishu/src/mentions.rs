//! Render only source-bound Host annotations, preserving literal text outside their ranges.
use crate::Error;
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Mention {
    pub start: usize,
    pub end: usize,
    account: String,
    native: String,
    label: String,
    assignment: Option<String>,
    source: i64,
}

pub fn read(args: &Value, text: &str) -> Result<Vec<Mention>, Error> {
    let mentions: Vec<Mention> = args
        .get("mentions")
        .map(|v| serde_json::from_value(v.clone()))
        .transpose()?
        .unwrap_or_default();
    let mut end = 0;
    for mention in &mentions {
        if mention.start < end
            || mention.start >= mention.end
            || text
                .get(mention.start..mention.end)
                .is_none_or(|s| !s.starts_with('@'))
            || mention.account.is_empty()
            || mention.native.is_empty()
            || mention.native.len() > 4096
            || mention.native.chars().any(char::is_control)
            || mention.label.is_empty()
            || mention.label.chars().count() > 128
            || mention.label.chars().any(char::is_control)
            || mention.assignment.as_ref().is_some_and(String::is_empty)
            || mention.source <= 0
        {
            return Err("invalid original account annotation".into());
        }
        end = mention.end;
    }
    Ok(mentions)
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

pub fn render(text: &str, mentions: &[Mention], start: usize, end: usize) -> Result<String, Error> {
    let mut output = String::new();
    let mut cursor = start;
    for mention in mentions.iter().filter(|m| m.end > start && m.start < end) {
        if mention.start < start || mention.end > end {
            return Err("native part cuts an original mention".into());
        }
        output.push_str(
            text.get(cursor..mention.start)
                .ok_or("invalid original text boundary")?,
        );
        output.push_str(&format!(
            "<at user_id=\"{}\">{}</at>",
            escape(&mention.native),
            escape(
                text.get(mention.start..mention.end)
                    .ok_or("invalid original label range")?
            )
        ));
        cursor = mention.end;
    }
    output.push_str(
        text.get(cursor..end)
            .ok_or("invalid original text boundary")?,
    );
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn native_id_and_label_are_escaped_only_in_original_ranges() {
        let text = "雪 @A<& rest";
        let mut args = json!({"mentions":[{"start":4,"end":8,"account":"original","native":"ou_\"<&", "label":"A<&", "assignment":"stage","source":1}]});
        let mentions = read(&args, text).unwrap();
        assert_eq!(
            render(text, &mentions, 0, text.len()).unwrap(),
            "雪 <at user_id=\"ou_&quot;&lt;&amp;\">@A&lt;&amp;</at> rest"
        );
        assert!(render(text, &mentions, 0, 5).is_err());
        args["mentions"][0]["start"] = json!(1);
        assert!(read(&args, text).is_err());
    }
}
