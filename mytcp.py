import asyncio
import random
from mytcputils import (
    FLAGS_FIN,
    FLAGS_SYN,
    FLAGS_RST,
    FLAGS_ACK,
    make_header,
    MSS,
    read_header,
    fix_checksum,
)


class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, flags, window_size, checksum, urg_ptr = read_header(
            segment
        )

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return

        payload = segment[4 * (flags >> 12):]
        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # TODO: talvez você precise passar mais coisas para o construtor de conexão
            serv_seq_no = random.randint(0, 0xFFFF)
            ack_segment = make_header(
                self.porta, src_port, serv_seq_no, seq_no + 1, FLAGS_SYN | FLAGS_ACK
            )
            self.rede.enviar(fix_checksum(ack_segment, src_addr, dst_addr), src_addr)
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, serv_seq_no, seq_no + 1)
            # TODO: você precisa fazer o handshake aceitando a conexão. Escolha se você acha melhor
            # fazer aqui mesmo ou dentro da classe Conexao.
            if self.callback:
                self.callback(conexao)
        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
        else:
            print(
                "%s:%d -> %s:%d (pacote associado a conexão desconhecida)"
                % (src_addr, src_port, dst_addr, dst_port)
            )


class Conexao:
    def __init__(self, servidor, id_conexao, my_seq, last_seq):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.my_seq = my_seq + 1
        self.timer = asyncio.get_event_loop().call_later(
            1, self._exemplo_timer
        )  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        # self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida

        self.last_seq = last_seq
        self.buffer = b''
        self.aberto = True
        # id_conexao = (src_addr, src_port, dst_addr, dst_port)

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print("Este é um exemplo de como fazer um timer")

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
        if not self.aberto:
            return
        if seq_no == self.last_seq and payload:
            self.last_seq = seq_no + len(payload)
            self.buffer += payload
            self.callback(self, payload)
            ack_segment = make_header(
                self.id_conexao[3], self.id_conexao[1], self.my_seq, self.last_seq, FLAGS_ACK
            )
            self.servidor.rede.enviar(fix_checksum(ack_segment, self.id_conexao[0], self.id_conexao[2]), self.id_conexao[0])
        elif (flags & FLAGS_FIN) == FLAGS_FIN:
            self.callback(self, b'')
            self.last_seq += 1
            ack_segment = make_header(
                self.id_conexao[3], self.id_conexao[1], self.my_seq, self.last_seq, FLAGS_ACK
            )
            self.servidor.rede.enviar(fix_checksum(ack_segment, self.id_conexao[0], self.id_conexao[2]), self.id_conexao[0])
            self.aberto = False
    # Os métodos abaixo fazem parte da API

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        if len(dados) / MSS <= 1:
            ack_segment = make_header(
                self.id_conexao[3], self.id_conexao[1], self.my_seq, self.last_seq, FLAGS_ACK
            )
            self.servidor.rede.enviar(fix_checksum(ack_segment + dados, self.id_conexao[0], self.id_conexao[2]), self.id_conexao[2])
        else:
            qtd = len(dados) // MSS
            for i in range(qtd):
                payload = dados[:MSS]
                ack_segment = make_header(
                    self.id_conexao[3], self.id_conexao[1], self.my_seq + len(payload), self.last_seq, FLAGS_ACK
                )
                self.servidor.rede.enviar(fix_checksum(ack_segment + payload, self.id_conexao[0], self.id_conexao[2]), self.id_conexao[2])
                self.my_seq += len(payload)
                dados = dados[MSS:]

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        ack_segment = make_header(
            self.id_conexao[3], self.id_conexao[1], self.my_seq, self.last_seq, FLAGS_ACK | FLAGS_FIN
        )
        self.servidor.rede.enviar(fix_checksum(ack_segment, self.id_conexao[0], self.id_conexao[2]), self.id_conexao[2])
