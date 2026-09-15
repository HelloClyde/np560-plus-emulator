# 手机与局域网试玩

2026-09-16：响应式布局、触控大按键、独立返回键、可折叠完整键盘与诊断。
真实矩阵、多指来源及松键租约沿用原输入机制；声音需要手动点击“启用声音”。
手机和电脑共用同一个模拟器，并非独立存档或独立会话，不要同时操作。

验证：24 项前端回归、触控时序测试、2 项转发脚本测试通过。
浏览器 320/390 px 竖屏及 844 px 横屏无页面横向溢出；390 px 常用键高度 48 px。
尚未进行真实手机触摸、音频与跨设备网络验收。

## 当前局域网开启状态

9 月 16 日重试启动成功：Windows 转发进程 PID 26540，监听 `192.168.31.89:8807`。
本机通过 LAN 地址访问首页返回 HTTP 200，状态 API 返回 running=true、240×120。
尚未验证真实手机跨设备访问；没有修改防火墙规则。
本机试玩仍为 http://127.0.0.1:8807/ 。

## 开启（不重启现有 QEMU）

在项目根目录的 Windows PowerShell 中执行，保持窗口开启；Ctrl+C 停止转发：

```powershell
python scripts/np560_lan_proxy.py --bind 192.168.31.89 --subnet 192.168.31.0/24
```

手机连接同一 Wi-Fi，打开 `http://192.168.31.89:8807/`。
这是当前以太网地址，DHCP 地址变化后需要同步修改；电脑连接有线、手机连接
同一路由器 Wi-Fi 也可以，但访客网络/AP 隔离可能阻止互访。

该转发只绑定上述 LAN IPv4，只接受指定子网，不监听 VPN 网卡。
无账号鉴权，子网内其他人也能操作模拟器；仅在可信家庭局域网使用。
不要进行路由器公网端口映射。停掉转发不影响本机模拟器。

若防火墙阻止手机访问，可由用户在**管理员 PowerShell**添加单端口规则：

```powershell
New-NetFirewallRule -Name NP560-LAN-8807 -DisplayName 'NP560 LAN 8807' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8807 -LocalAddress 192.168.31.89 -RemoteAddress 192.168.31.0/24 -Profile Private
```

撤销该规则：`Remove-NetFirewallRule -Name NP560-LAN-8807`。
不关闭防火墙，不放开全部 Python 端口，不修改公共网络配置。

## WSL 直接监听选项

`scripts/run-np560-web.ps1` 新增 `-ListenAddress`，默认仍为 `127.0.0.1`。
`-ListenAddress 0.0.0.0` 仅改变 WSL 服务监听地址，不保证 Windows NAT、防火墙
和手机访问路径已打通。当前实例可用上述 Windows 转发，无需重启丢失运行状态。
