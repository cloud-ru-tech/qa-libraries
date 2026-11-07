FROM alpine:3.24.3

RUN apk add --no-cache openssh-server openssh-client sudo \
    && adduser -D -s /bin/sh testuser \
    && echo "testuser:testpass" | chpasswd \
    && echo "testuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && mkdir -p /etc/ssh/keys /etc/ssh/authorized

EXPOSE 22
# Ключи монтируются из каталогов pytest, их владелец не root и не testuser, поэтому StrictModes отключён.
CMD ["/usr/sbin/sshd", "-D", "-e", \
    "-h", "/etc/ssh/keys/ssh_host_rsa_key", \
    "-o", "AuthorizedKeysFile=/etc/ssh/authorized/authorized_keys", \
    "-o", "StrictModes=no"]
