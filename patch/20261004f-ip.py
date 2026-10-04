# -*- coding: utf-8 -*-
"""把 APP 里写死的后端地址改成 192.168.1.133:8000。在仓库根目录跑。
"""
import ast
import sys

SRC = "app/lib/api.dart"

OLD = r'''  static String base = "http://192.168.10.147:8000";'''
NEW = r'''  /// 后端地址。
  /// 后端跟 APP 跑在同一台机器上时可以用 127.0.0.1；要让别人也能连进来，
  /// 就得填这台机器的局域网 IP（注意：路由器重新分配后 IP 会变）。
  static String base = "http://192.168.1.133:8000";'''


def main():
    s = open(SRC, encoding="utf-8").read()
    n = s.count(OLD)
    if n != 1:
        print("!! api.dart 里那一行匹配了 %d 次（应该是 1），整体不动" % n)
        return 1
    s = s.replace(OLD, NEW, 1)
    open(SRC, "w", encoding="utf-8").write(s)
    print("OK app/lib/api.dart 的后端地址改成 192.168.1.133:8000")
    return 0


sys.exit(main())
