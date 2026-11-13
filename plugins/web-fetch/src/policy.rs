use std::{
    collections::HashSet,
    net::{IpAddr, ToSocketAddrs},
};
use url::Url;

pub fn url(input: &str) -> Result<Url, &'static str> {
    if input.len() > 8192 {
        return Err("url_too_long");
    }
    let mut url = Url::parse(input).map_err(|_| "invalid_url")?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("invalid_url");
    }
    url.set_fragment(None);
    Ok(url)
}

pub(crate) fn public(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(addr) => {
            let [a, b, c, _] = addr.octets();
            !matches!(a, 0 | 10 | 127 | 224..=255)
                && !(a == 100 && (64..128).contains(&b)
                    || a == 169 && b == 254
                    || a == 172 && (16..32).contains(&b)
                    || a == 192 && (b == 168 || b == 0 && matches!(c, 0 | 2) || b == 88 && c == 99)
                    || a == 198 && (matches!(b, 18 | 19) || b == 51 && c == 100)
                    || a == 203 && b == 0 && c == 113)
        }
        IpAddr::V6(addr) => {
            let s = addr.segments();
            (0x2000..0x4000).contains(&s[0])
                && !(s[0] == 0x2001 && (s[1] < 0x200 || s[1] == 0xdb8)
                    || s[0] == 0x2002
                    || s[0] == 0x3fff && s[1] < 0x1000)
        }
    }
}

pub fn check_addresses(addrs: &[IpAddr], local: &HashSet<IpAddr>) -> Result<(), &'static str> {
    if addrs.is_empty() {
        return Err("dns_empty");
    }
    if addrs.iter().any(|ip| !public(*ip) || local.contains(ip)) {
        return Err("destination_denied");
    }
    Ok(())
}

pub fn resolve(url: &Url) -> Result<Vec<IpAddr>, &'static str> {
    let host = url
        .host_str()
        .ok_or("invalid_url")?
        .trim_matches(['[', ']']);
    if host.trim_end_matches('.').eq_ignore_ascii_case("localhost") {
        return Err("destination_denied");
    }
    let port = url.port_or_known_default().ok_or("invalid_url")?;
    let mut addrs: Vec<_> = (host, port)
        .to_socket_addrs()
        .map_err(|_| "dns_failed")?
        .map(|s| s.ip())
        .collect();
    addrs.sort_unstable();
    addrs.dedup();
    let local = if_addrs::get_if_addrs()
        .map_err(|_| "host_address_unknown")?
        .into_iter()
        .map(|i| i.ip())
        .collect();
    check_addresses(&addrs, &local)?;
    Ok(addrs)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn never_choose_one_public_answer_from_a_mixed_set() {
        let a = "93.184.216.34".parse().unwrap();
        for bad in [
            "127.0.0.1",
            "169.254.169.254",
            "10.0.1.1",
            "::1",
            "::ffff:127.0.0.1",
            "2002:7f00:1::1",
        ] {
            assert_eq!(
                check_addresses(&[a, bad.parse().unwrap()], &HashSet::new()),
                Err("destination_denied")
            );
        }
        assert_eq!(
            check_addresses(&[a], &HashSet::from([a])),
            Err("destination_denied")
        );
    }
}
