#!/usr/bin/env python
import ast
import pathlib
import sys

FORBIDDEN_BUILTIN_GENERICS = {"dict", "frozenset", "list", "set", "tuple", "type"}


class CompatibilityVisitor(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.issues = []

    def visit_AnnAssign(self, node):
        self._check_annotation(node.annotation, node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._check_function_annotations(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self._check_function_annotations(node)
        self.generic_visit(node)

    def _check_function_annotations(self, node):
        arg_groups = [
            node.args.posonlyargs,
            node.args.args,
            node.args.kwonlyargs,
        ]
        for group in arg_groups:
            for arg in group:
                self._check_annotation(arg.annotation, arg.lineno)
        if node.args.vararg:
            self._check_annotation(node.args.vararg.annotation, node.args.vararg.lineno)
        if node.args.kwarg:
            self._check_annotation(node.args.kwarg.annotation, node.args.kwarg.lineno)
        self._check_annotation(node.returns, node.lineno)

    def _check_annotation(self, annotation, lineno):
        if annotation is None:
            return

        for node in ast.walk(annotation):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                if node.value.id in FORBIDDEN_BUILTIN_GENERICS:
                    self.issues.append(
                        (lineno, "Use typing.%s[...] instead of built-in %s[...] for Python 3.8 compatibility"
                         % (node.value.id.title(), node.value.id))
                    )
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                self.issues.append(
                    (lineno, "Use typing.Optional/Union instead of PEP 604 '|' unions for Python 3.8 compatibility")
                )


def iter_python_files(path):
    if path.is_file() and path.suffix == ".py":
        yield path
        return

    if path.is_dir():
        for file_path in sorted(path.rglob("*.py")):
            yield file_path


def scan_file(path):
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8-sig")

    tree = ast.parse(source, filename=str(path))
    visitor = CompatibilityVisitor(path)
    visitor.visit(tree)
    return visitor.issues


def main(argv):
    if len(argv) < 2:
        print("Usage: check_embedded_python_compat.py <path> [<path> ...]", file=sys.stderr)
        return 2

    issues = []
    for raw_path in argv[1:]:
        path = pathlib.Path(raw_path).resolve()
        for file_path in iter_python_files(path):
            for lineno, message in scan_file(file_path):
                issues.append((file_path, lineno, message))

    if issues:
        print("Embedded Python compatibility check failed:\n", file=sys.stderr)
        for file_path, lineno, message in issues:
            print("%s:%s: %s" % (file_path, lineno, message), file=sys.stderr)
        return 1

    print("Embedded Python compatibility check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
