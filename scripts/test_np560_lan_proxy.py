"""Exercise the TCP bridge locally without exposing a LAN listener."""
import asyncio
import unittest
from np560_lan_proxy import serve


class LanProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_lan_bind_required(self):
        for bind, subnet in [("0.0.0.0", "0.0.0.0/0"),
                             ("127.0.0.1", "192.168.31.0/24")]:
            with self.assertRaises(ValueError):
                await serve(bind, 0, subnet, 1)

    async def test_bidirectional_binary_transport(self):
        async def echo(reader, writer):
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        reservation = await asyncio.start_server(echo, "127.0.0.1", 0)
        port = reservation.sockets[0].getsockname()[1]
        reservation.close()
        await reservation.wait_closed()
        proxy = asyncio.create_task(serve("127.0.0.1", port, "127.0.0.0/8",
                                          upstream.sockets[0].getsockname()[1]))
        try:
            for attempt in range(100):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    break
                except ConnectionRefusedError:
                    await asyncio.sleep(.01)
            else:
                self.fail("bridge did not start")
            payload = bytes(range(256)) * 1024
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 5), payload)
            writer.close()
            await writer.wait_closed()
        finally:
            proxy.cancel()
            await asyncio.gather(proxy, return_exceptions=True)
            upstream.close()
            await upstream.wait_closed()


if __name__ == "__main__":
    unittest.main()
