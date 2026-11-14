FROM alpine:3.24.3

RUN apk add --no-cache openssh-server openssh-client sudo \
    && adduser -D -s /bin/sh testuser \
    && echo "testuser:testpass" | chpasswd \
    && echo "testuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && mkdir -p /etc/ssh/keys /etc/ssh/authorized

EXPOSE 22
# Keys are mounted from pytest directories owned by neither root nor testuser, so StrictModes is disabled.
CMD ["/usr/sbin/sshd", "-D", "-e", \
    "-h", "/etc/ssh/keys/ssh_host_rsa_key", \
    "-o", "AuthorizedKeysFile=/etc/ssh/authorized/authorized_keys", \
    "-o", "StrictModes=no"]
