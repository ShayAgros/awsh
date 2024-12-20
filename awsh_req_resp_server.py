import asyncore
import asynchat
import socket
import threading

import time
import logging
import errno
from typing import Tuple

AWHS_PORT=7007
AWSH_ACK_STR='AWSHACK'
AWSH_RESULT_STR='AWSHRESULT'

# Useful for the future
# from functools import wraps
# from time import time
# def measure(func):
    # @wraps(func)
    # def _time_it(*args, **kwargs):
        # start = int(round(time() * 1000))
        # try:
            # return func(*args, **kwargs)
        # finally:
            # end_ = int(round(time() * 1000)) - start
            # print(f"Total execution time: {end_ if end_ > 0 else 0} ms")
    # return _time_it

class request_item:
    def __init__(self, connection, request_id):
        self.request_id = request_id
        self.connection = connection
        return

    def complete_request(self, reply = '', status = 0):
        self.connection.complete_request(self.request_id, reply, status)


class awsh_connection(asynchat.async_chat):

    def __init__(self, sock, request_object):
        asynchat.async_chat.__init__(self, sock=sock)

        self.logger = logging.getLogger("awsh_connection")

        self.logger.debug('created awsh connection')
        self.received_data = []
        self.request_object = request_object

        self.set_terminator(b"\n")


    def collect_incoming_data(self, data):
        """Read an incoming request from the client and store it in the request
        queue"""
        self.logger.debug('Received partial message: ' + str(data))
        ddata = data.decode('ascii')
        self.received_data.append(ddata)


    # override default push function. It's the same as in asynchat but without
    # initiating the send explicitly. The asyncore.loop() takes care to do so
    def push(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError('data argument must be byte-ish (%r)',
                            type(data))
        sabs = self.ac_out_buffer_size
        if len(data) > sabs:
            for i in range(0, len(data), sabs):
                self.producer_fifo.append(data[i:i+sabs])
        else:
            self.producer_fifo.append(data)


    def found_terminator(self):
        # We received a request. Ack it, and put it into processing

        self.logger.debug('Received request: ' +  ' '.join(self.received_data))

        request_command = ' '.join(self.received_data).split()
        req_id = int(request_command[0])
        req_item = request_item(self, req_id)

        ack_str = '{} {}{}'.format(req_id, AWSH_ACK_STR, '\n')
        ack = bytes(ack_str, 'ascii')
        self.push(ack)

        def process_request():
            try:
                self.request_object.process_request(request_command[1:], req_item)
            except Exception as e:
                self.logger.error("Got an exception for request")
                self.logger.error(str(e.with_traceback))
                req_item.complete_request(reply=str(e), status = 1)

            return

        job = threading.Thread(target=process_request)
        job.start()

        self.received_data = []


    def complete_request(self, req_id, response, success):
        reply = '{} {} {} {}{}'.format(req_id, AWSH_RESULT_STR, int(success), response, '\n')
        reply_bytes = bytes(reply, 'ascii')

        self.logger.debug (f'completed request id {req_id} (size {len(reply_bytes)})')
        # reply the response
        self.push(reply_bytes)
        # close connection on your side
        # self.close()


class awsh_req_server(asyncore.dispatcher):
    """This server waits for requests and passes them to @request_object using
    its process_request method."""

    use_encoding = 0
    encoding = 'latin-1'

    def __init__(self, request_object):

        assert getattr(request_object, 'process_request', None) != None

        self.logger = logging.getLogger("awsh_req_server")

        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)

        self.logger.info("Started async server on port {}".format(AWHS_PORT))

        self.request_object = request_object

        self.bind(('localhost', AWHS_PORT))
        self.address = self.socket.getsockname()
        return


    def start_server(self):
        self.listen(5)


    def handle_accept(self):
        self.logger.debug("Accepted a connection")
        client_info = self.accept()
        awsh_connection(sock = client_info[0],
                        request_object = self.request_object)


    def handle_close(self):
        self.logger.info('server: closing server')
        self.close()


class awsh_req_client(asynchat.async_chat):
    """This client communicates with a awsh_req_server server. It sends it
    requests and receives the reply from it asynchronously (might be in a
    different order than originally sent)"""

    def __init__(self, fail_if_no_server=False, synchronous=False):

        # We're gonna loop over existing sockets if we're waiting for them to
        # complete
        if synchronous:
            self.socket_map = dict()
        else:
            self.socket_map = None

        asynchat.async_chat.__init__(self, map=self.socket_map)

        self.logger = logging.getLogger("awsh_req_client")
        # coloredlogs.install(level='DEBUG', logger=logger)
        # self.logger = logging.basicConfig(level=logging.DEBUG)
        self.logger.info('started awsh client')

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)

        self.next_request_id = 0
        # this would hold each request from client by request id
        self.pending_commands = dict()
        # per request id reply queue
        # self.received_replies = dict()
        self.received_reply = list()

        self.logger.debug('connecting')

        self.socket.setblocking(fail_if_no_server)
        # err = self.socket.connect_ex(('localhost', AWHS_PORT))
        # if err:
            # print(f"error is {err} ({errno.errorcode[err]})")
        self.connect(('localhost', AWHS_PORT))


    def handle_connect(self):
        self.logger.debug('client: connection succeeded')
        self.set_terminator(b"\n")
        # self.push(b"hello world\n")

    def is_synchronous(self):
        return self.socket_map is not None

    def collect_incoming_data(self, data):
        # print('client: received data ' + str(data), flush=True)

        self.logger.debug(f'Received partial mesasge of len {len(data)}')
        self.received_reply.append(data)


    def _find_next_space(self, msg : str) -> Tuple[str, str]:
        """Parse the next word starting @msg start up until you next space, and
        return remaining string after that (not including the space)"""
        i = 0
        for char in msg:
            if char == ' ':
                break

            i = i + 1

        return msg[:i], msg[i + 1:]

    def found_terminator(self):

        logger = self.logger

        decoded_data_arr = map(lambda e : str(e, 'ascii'), self.received_reply)
        reply = ''.join(decoded_data_arr)
        self.received_reply = []

        logger.debug(f"Received reply of length {len(reply)}")

        pending_commands = self.pending_commands

        # print(reply)

        # reply = received_reply.split()
        req_id, msg = self._find_next_space(reply)
        print("req_id", req_id)
        if not req_id in pending_commands:
            logger.error("Received reply for unexisting req id {}".format(req_id))
            return

        reply_type, msg = self._find_next_space(msg)
        print("reply_type", reply_type)

        if reply_type == AWSH_ACK_STR:
            if pending_commands[req_id]['ack']:
                logger.error("client: Received ack for already acknowledged command. req id: {}".format(req_id))
            else:
                logger.debug("client: Acked. req id: {}".format(req_id))
                pending_commands[req_id]['ack'] = True
            return
        elif not pending_commands[req_id]['ack']:
            logger.error("Received reply_type for a request that hasn't been acked")
            return

        if reply_type != AWSH_RESULT_STR:
            logger.error("client: invalid reply type (neither ack or result code): type = " + reply_type)
            logger.error("client: closing connection")
            self.close()
            return

        logger.debug("client: Received response. req id: {}".format(req_id))

        status, msg = self._find_next_space(msg)
        request_success = int(status)

        # parse the response
        # if len(reply) > 3:
            # request_response = ''.join(reply[3:])
        # else:
            # request_response = ''

        # logger.debug(f"received reply_type: {request_response}")
        response_handler = pending_commands[req_id]['res_handler']

        if not response_handler:
            logger.debug('No respond handler. Doing nothing with the reply')
        else:
            response_handler(self, request_success, msg)


    def send_request(self, request, response_handler = None):

        self.logger.debug(f'client: sending request {request}')

        req_id = str(self.next_request_id)

        self.pending_commands[req_id] = { 'ack': False,
                                          'res_handler': response_handler
                                        }

        request = '{} {}{}'.format(req_id, request, '\n')
        request = bytes(request, 'ascii')
        producer = asynchat.simple_producer(request)
        self.push_with_producer(producer)

        self.next_request_id = self.next_request_id + 1

    def send_request_blocking(self, request):
        """Send a command to the server and block until it returns.

        This function returns the server's response"""

        global response
        response = None

        def handle_reply(connection, response_success, server_reply):
            global response
            response = response_success, server_reply
            print("Got blocking request response")

            connection.close()

        self.send_request(request, handle_reply)

        asyncore.loop(map=self.socket_map)

        print("done looping")

        return response


class test_class:

    def process_request(self, request, connection):
        """This function is the needs to be implemented for awsh_req_server.
           It is called each time a request is submitted."""

        connection.complete_request()


def start_requests_server(req_server):
    req_server.start_server()
    asyncore.loop(timeout=0.5)

if __name__ == '__main__':
    """ testing """

    # server = awsh_req_server(test_class())
    client = awsh_req_client()

    def handle_response(connection, response_success, server_reply):
        connection.close()

    print('sending request')

    client.send_request('1 us-east-1', response_handler=handle_response)

    # client.close()

    # comm = threading.Thread(target=asyncore.loop)
    # comm.daemon = True
    # comm.start()

    # while True:
        # client.push(b'message')
        # time.sleep(0.1)

    asyncore.loop(map=client.socket_map)
