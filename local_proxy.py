"""本地 HTTP 代理 - 转发到住宅代理（asyncio 实现）"""
import asyncio, sys

PROXY_HOST = "gate.decodo.com"
PROXY_PORT = 10001
PROXY_AUTH = "Basic " + __import__("base64").b64encode(b"sp2senzuf2:vto~iJQ30kEa6Ghvm5").decode()

async def forward(src, dst):
    try:
        while True:
            data = await asyncio.wait_for(src.read(65536), timeout=30)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except:
        pass

async def handle_client(reader, writer):
    try:
        req = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        first_line = req.split(b"\r\n")[0].decode(errors='replace')
        print(f"[REQ] {first_line[:80]}")
        
        remote_r, remote_w = await asyncio.wait_for(
            asyncio.open_connection(PROXY_HOST, PROXY_PORT), timeout=10)
        
        if first_line.startswith("CONNECT"):
            host_port = first_line.split()[1]
            # 发送 CONNECT 到远程代理（必须带 Host 头）
            connect_req = f"CONNECT {host_port} HTTP/1.1\r\nHost: {host_port}\r\nProxy-Authorization: {PROXY_AUTH}\r\n\r\n"
            remote_w.write(connect_req.encode())
            await remote_w.drain()
            
            resp = await asyncio.wait_for(remote_r.readuntil(b"\r\n\r\n"), timeout=10)
            if b"200" in resp:
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()
            else:
                writer.write(resp)
                await writer.drain()
                remote_w.close()
                return
            
            await asyncio.gather(
                forward(reader, remote_w),
                forward(remote_r, writer)
            )
        else:
            # HTTP - 添加认证头
            lines = req.split(b"\r\n")
            has_auth = any(l.lower().startswith(b"proxy-authorization:") for l in lines)
            if not has_auth:
                insert_at = lines.index(b"") if b"" in lines else len(lines)
                lines.insert(insert_at, f"Proxy-Authorization: {PROXY_AUTH}".encode())
            remote_w.write(b"\r\n".join(lines))
            await remote_w.drain()
            
            # 读取响应并返回
            resp = b""
            while True:
                chunk = await asyncio.wait_for(remote_r.read(65536), timeout=30)
                if not chunk:
                    break
                resp += chunk
            writer.write(resp)
            await writer.drain()
        
        remote_w.close()
        writer.close()
    except Exception as e:
        print(f"[ERR] {e}")
        try: writer.close()
        except: pass

async def main(port):
    server = await asyncio.start_server(handle_client, "127.0.0.1", port)
    print(f"本地代理: 127.0.0.1:{port} → {PROXY_HOST}:{PROXY_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 18888))
