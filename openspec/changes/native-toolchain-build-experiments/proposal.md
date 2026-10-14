# Fixed native toolchain build experiments

The UID membership/cleanup fixtures now pass in disposable macOS CI. Exercise real
pinned uv/Python, Node child-build and Go stdlib build recipes under that UID model.
These are protected fixed compatibility experiments, outside the shipping runtime.
They neither grant general forks nor establish production containment or Slice C
acceptance. Eventu's verified scope fix is already applied without mixing older work.
