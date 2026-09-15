#!/usr/bin/env python3
"""LAN-only TCP bridge to the existing loopback Web emulator (no guest restart)."""
import argparse
import asyncio
import ipaddress


async def serve(bind, port, subnet, target_port):
    allowed = ipaddress.ip_network(subnet, strict=False)
    if ipaddress.ip_address(bind) not in allowed or bind == "0.0.0.0":
        raise ValueError("Bind an explicit address inside the allowed LAN subnet")

    async def client(reader, writer):
        remote = ipaddress.ip_address(writer.get_extra_info("peername")[0])
        upstream = None
        tasks = []
        try:
            if remote not in allowed:
                return
            upstream_reader, upstream = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", target_port), 5)

            async def copy(source, destination):
                while data := await source.read(65536):
                    destination.write(data)
                    await destination.drain()

            tasks = [asyncio.create_task(copy(reader, upstream)),
                     asyncio.create_task(copy(upstream_reader, writer))]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (writer, upstream):
                if stream is not None:
                    stream.close()
                    try:
                        await stream.wait_closed()
                    except OSError:
                        pass

    server = await asyncio.start_server(client, bind, port)
    print(f"NP560 LAN http://{bind}:{port}/ -> 127.0.0.1:{target_port}; peers {allowed}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--subnet", required=True)
    parser.add_argument("--port", type=int, default=8807)
    parser.add_argument("--target-port", type=int, default=8807)
    args = parser.parse_args()
    asyncio.run(serve(args.bind, args.port, args.subnet, args.target_port))
