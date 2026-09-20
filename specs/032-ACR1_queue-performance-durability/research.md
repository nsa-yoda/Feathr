# Research

The local queue used a list scan for every receive and expiry lookup, which became linear in backlog size. A deque plus expiry heap keeps ordinary send/receive scheduling indexed while retaining the existing deterministic clock seam.
