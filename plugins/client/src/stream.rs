use std::io::{self, Read, Write};
use tiny_http::Request;

// Flush each original byte chunk. tiny_http's normal response encoder buffers
// small chunks, which would hide a lone committed SSE hint until another update.
// There is no local event queue, cursor, replay, or fabricated SSE frame.
pub fn respond(request: Request, upstream: ureq::http::Response<ureq::Body>) -> io::Result<()> {
    if upstream
        .headers()
        .get("Content-Type")
        .and_then(|v| v.to_str().ok())
        .is_none_or(|v| v.split(';').next() != Some("text/event-stream"))
    {
        return request.respond(tiny_http::Response::empty(502));
    }
    let mut writer = request.into_writer();
    writer.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\nTransfer-Encoding: chunked\r\n\r\n")?;
    writer.flush()?;
    let mut reader = upstream.into_body().into_reader();
    let mut chunk = [0; 8192];
    loop {
        let n = reader.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        write!(writer, "{n:x}\r\n")?;
        writer.write_all(&chunk[..n])?;
        writer.write_all(b"\r\n")?;
        writer.flush()?;
    }
    writer.write_all(b"0\r\n\r\n")?;
    writer.flush()
}
