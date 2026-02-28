#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
#include <fcntl.h>
#include <errno.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/epoll.h>
#include <sys/time.h>
#include <netinet/ip_icmp.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <time.h>

#define MAX_EVENTS 10
#define ICMP_COUNT 20
#define UDP_PACKET 1400
#define TOKEN_RATE 5000000.0
#define BUCKET_SIZE 1000000.0
#define TWAMP_PORT 862

int set_nonblocking(int fd) {
    return fcntl(fd, F_SETFL,
        fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
}

unsigned short checksum(void *b, int len) {
    unsigned short *buf = b;
    unsigned int sum = 0;
    for (; len > 1; len -= 2)
        sum += *buf++;
    if (len == 1)
        sum += *(unsigned char*)buf;
    sum = (sum >> 16) + (sum & 0xFFFF);
    sum += (sum >> 16);
    return ~sum;
}

typedef struct {
    double tokens;
    double rate;
    double bucket_size;
    struct timespec last;
} token_bucket;

void tb_init(token_bucket *tb,
             double rate,
             double bucket_size) {
    tb->tokens = bucket_size;
    tb->rate = rate;
    tb->bucket_size = bucket_size;
    clock_gettime(CLOCK_MONOTONIC, &tb->last);
}

void tb_update(token_bucket *tb) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    double elapsed =
        (now.tv_sec - tb->last.tv_sec) +
        (now.tv_nsec - tb->last.tv_nsec)/1e9;

    tb->tokens += elapsed * tb->rate;
    if (tb->tokens > tb->bucket_size)
        tb->tokens = tb->bucket_size;

    tb->last = now;
}

int tb_consume(token_bucket *tb, double size) {
    tb_update(tb);
    if (tb->tokens >= size) {
        tb->tokens -= size;
        return 1;
    }
    return 0;
}

double rfc3393_jitter(double *delays, int count) {
    if (count < 2) return 0;
    double sum = 0;
    for (int i = 1; i < count; i++)
        sum += fabs(delays[i] - delays[i-1]);
    return sum / (count - 1);
}

double icmp_delays[ICMP_COUNT];
int icmp_received = 0;

void enable_timestamping(int sock) {
    int val = 1;
    setsockopt(sock, SOL_SOCKET,
               SO_TIMESTAMPNS, &val, sizeof(val));
}

double timespec_diff_ms(struct timespec *a,
                        struct timespec *b) {
    return (b->tv_sec - a->tv_sec) * 1000.0 +
           (b->tv_nsec - a->tv_nsec) / 1e6;
}

void snmpv3_poll(char *host) {

    netsnmp_session session, *ss;
    snmp_sess_init(&session);

    session.peername = host;
    session.version = SNMP_VERSION_3;

    session.securityName = strdup("slauser");
    session.securityNameLen = strlen(session.securityName);
    session.securityLevel = SNMP_SEC_LEVEL_AUTHPRIV;

    session.securityAuthProto = usmHMACSHA1AuthProtocol;
    session.securityAuthProtoLen = USM_AUTH_PROTO_SHA_LEN;
    session.securityPrivProto = usmAESPrivProtocol;
    session.securityPrivProtoLen = USM_PRIV_PROTO_AES_LEN;

    generate_Ku(session.securityAuthProto,
        session.securityAuthProtoLen,
        (u_char*)"authpass", 8,
        session.securityAuthKey,
        &session.securityAuthKeyLen);

    generate_Ku(session.securityPrivProto,
        session.securityPrivProtoLen,
        (u_char*)"privpass", 8,
        session.securityPrivKey,
        &session.securityPrivKeyLen);

    ss = snmp_open(&session);
    if (!ss) return;

    oid anOID[MAX_OID_LEN];
    size_t anOID_len = MAX_OID_LEN;
    read_objid(".1.3.6.1.2.1.2.2.1.14.1", anOID, &anOID_len);

    netsnmp_pdu *pdu = snmp_pdu_create(SNMP_MSG_GET);
    snmp_add_null_var(pdu, anOID, anOID_len);

    netsnmp_pdu *response;
    int status = snmp_synch_response(ss, pdu, &response);

    if (status == STAT_SUCCESS &&
        response->errstat == SNMP_ERR_NOERROR) {

        for (netsnmp_variable_list *vars =
             response->variables;
             vars;
             vars = vars->next_variable) {

            printf("SNMP ifInErrors: %ld\n",
                   *vars->val.integer);
        }
    }

    if (response)
        snmp_free_pdu(response);

    snmp_close(ss);
}


SSL_CTX* init_tls() {
    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    SSL_CTX_set_verify(ctx,
        SSL_VERIFY_PEER, NULL);

    SSL_CTX_load_verify_locations(ctx,
        "ca.pem", NULL);

    SSL_CTX_use_certificate_file(ctx,
        "client.crt", SSL_FILETYPE_PEM);

    SSL_CTX_use_PrivateKey_file(ctx,
        "client.key", SSL_FILETYPE_PEM);

    return ctx;
}

void tls_report(char *backend, int port,
                double jitter,
                double one_way,
                double asymmetry) {

    SSL_CTX *ctx = init_tls();
    int sock = socket(AF_INET, SOCK_STREAM, 0);

    struct sockaddr_in server;
    server.sin_family = AF_INET;
    server.sin_port = htons(port);
    server.sin_addr.s_addr = inet_addr(backend);

    connect(sock,
        (struct sockaddr*)&server,
        sizeof(server));

    SSL *ssl = SSL_new(ctx);
    SSL_set_fd(ssl, sock);

    if (SSL_connect(ssl) <= 0) {
        printf("TLS failed\n");
        return;
    }

    if (SSL_get_verify_result(ssl)
        != X509_V_OK) {
        printf("Cert invalid\n");
        return;
    }

    char json[512];
    sprintf(json,
        "{\"jitter\":%.3f,"
        "\"one_way\":%.3f,"
        "\"asymmetry\":%.3f}\n",
        jitter, one_way, asymmetry);

    SSL_write(ssl, json, strlen(json));

    SSL_free(ssl);
    close(sock);
    SSL_CTX_free(ctx);
}


double twamp_test(char *server) {

    int sock = socket(AF_INET,
                      SOCK_DGRAM, 0);

    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(TWAMP_PORT);
    addr.sin_addr.s_addr =
        inet_addr(server);

    struct timespec send_ts;
    clock_gettime(CLOCK_REALTIME,
                  &send_ts);

    sendto(sock, &send_ts,
           sizeof(send_ts), 0,
           (struct sockaddr*)&addr,
           sizeof(addr));

    struct timespec recv_ts;
    socklen_t len = sizeof(addr);

    recvfrom(sock, &recv_ts,
             sizeof(recv_ts), 0,
             (struct sockaddr*)&addr,
             &len);

    close(sock);

    return timespec_diff_ms(&send_ts,
                            &recv_ts);
}

int main(int argc, char *argv[]) {

    if (argc != 4) {
        printf("Usage: %s "
               "<target_ip> "
               "<backend_ip> "
               "<snmp_host>\n",
               argv[0]);
        return 1;
    }

    char *target = argv[1];
    char *backend = argv[2];
    char *snmp_host = argv[3];

    int ep = epoll_create1(0);

    int icmp_sock = socket(AF_INET,
                           SOCK_RAW,
                           IPPROTO_ICMP);

    set_nonblocking(icmp_sock);
    enable_timestamping(icmp_sock);

    struct epoll_event ev;
    ev.events = EPOLLIN;
    ev.data.fd = icmp_sock;
    epoll_ctl(ep, EPOLL_CTL_ADD,
              icmp_sock, &ev);

    token_bucket bucket;
    tb_init(&bucket,
            TOKEN_RATE,
            BUCKET_SIZE);

    struct sockaddr_in dest;
    dest.sin_family = AF_INET;
    dest.sin_addr.s_addr =
        inet_addr(target);

    char udp_buffer[UDP_PACKET];
    memset(udp_buffer, 'A',
           sizeof(udp_buffer));

    while (1) {

        /* Controlled UDP rate */
        if (tb_consume(&bucket,
            UDP_PACKET * 8)) {

            sendto(icmp_sock,
                udp_buffer,
                UDP_PACKET, 0,
                (struct sockaddr*)&dest,
                sizeof(dest));
        }

        double rtt =
            twamp_test(target);

        icmp_delays[icmp_received++ %
            ICMP_COUNT] = rtt;

        double jitter =
            rfc3393_jitter(
                icmp_delays,
                ICMP_COUNT);

        double one_way = rtt / 2.0;

        double reverse = rtt - one_way;
        double asymmetry =
            fabs(one_way - reverse);

        printf("Jitter: %.3f ms\n", jitter);
        printf("OneWay: %.3f ms\n", one_way);
        printf("Asymmetry: %.3f ms\n",
               asymmetry);

        snmpv3_poll(snmp_host);

        tls_report(backend, 443,
                   jitter,
                   one_way,
                   asymmetry);

        sleep(10);
    }

    return 0;
}