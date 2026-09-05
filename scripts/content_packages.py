"""Build-time content selection. A package uses the same layout as a work."""
from pathlib import Path


class ContentPackages:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config = config or {}
        packages = self.config.get('packages', {})
        enabled = self.config.get('enabled', [])
        if not isinstance(packages, dict) or not isinstance(enabled, list):
            raise ValueError('content requires packages mapping and enabled list')
        self.selected = []
        visiting = set()
        groups = {}

        def visit(name):
            if name in visiting:
                raise ValueError(f'Content dependency cycle: {name}')
            if name in self.selected:
                return
            if name not in packages:
                raise ValueError(f'Unknown content package: {name}')
            package = packages[name]
            visiting.add(name)
            for dependency in package.get('requires', []):
                visit(dependency)
            visiting.remove(name)
            group = package.get('exclusive_group')
            if group and group in groups:
                raise ValueError(f'Exclusive content packages: {groups[group]}, {name}')
            if group:
                groups[group] = name
            self.selected.append(name)

        for name in enabled:
            visit(name)
        self.roots = [self.root]
        all_roots = []
        named_roots = {}
        for name, package in packages.items():
            path = (self.root / package['root']).resolve()
            if path == self.root or self.root not in path.parents:
                raise ValueError(f'Package root must be inside work: {name}')
            if any(path == other or path in other.parents or other in path.parents for other in all_roots):
                raise ValueError(f'Overlapping package roots: {name}')
            all_roots.append(path)
            named_roots[name] = path
            if name in self.selected:
                if not path.is_dir():
                    raise ValueError(f'Missing selected package directory: {path}')
        self.roots.extend(named_roots[name] for name in self.selected)
        self.package_roots = all_roots

    def files(self, patterns):
        found = set()
        for root in self.roots:
            for pattern in patterns:
                if Path(pattern).is_absolute():
                    try:
                        pattern = str(Path(pattern).resolve().relative_to(self.root))
                    except ValueError:
                        raise ValueError(f'Content path escapes work: {pattern}')
                if '..' in Path(pattern).parts:
                    raise ValueError(f'Content paths must be relative to work/package: {pattern}')
                for path in sorted(root.glob(pattern)):
                    resolved = path.resolve()
                    if not path.is_file():
                        continue
                    if root not in resolved.parents:
                        raise ValueError(f'Content file escapes root: {path}')
                    # A broad common glob must never absorb inactive packages.
                    if root == self.root and any(p == resolved or p in resolved.parents for p in self.package_roots):
                        continue
                    if resolved not in found:
                        found.add(resolved)
                        yield resolved
