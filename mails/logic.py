"""Tiny boolean expression parser for rule logic.

Grammar (case-insensitive):
    expr   := term (OR term)*
    term   := factor (AND factor)*
    factor := NOT factor | "(" expr ")" | LETTER
Tokens: AND/&, OR/|, NOT/!, letters A-Z, parentheses.
"""

import re


class LogicError(ValueError):
    pass


TOKEN_RE = re.compile(
    r"\s*(\(|\)|!|&&|\|\||[Aa][Nn][Dd]|[Oo][Rr]|[Nn][Oo][Tt]|[A-Z])"
)


def tokenize(expression):
    tokens = []
    i = 0
    while i < len(expression):
        m = TOKEN_RE.match(expression, i)
        if not m:
            if expression[i:].strip() == "":
                break
            raise LogicError(
                "Unexpected character: %r" % expression[i:].strip()[0]
            )
        token = m.group(1).upper()
        if token == "AND":
            tokens.append(("AND", None))
        elif token == "OR":
            tokens.append(("OR", None))
        elif token == "NOT" or token == "!":
            tokens.append(("NOT", None))
        elif token in ("&&", "&"):
            tokens.append(("AND", None))
        elif token in ("||", "|"):
            tokens.append(("OR", None))
        elif token == "(" or token == ")":
            tokens.append((token, None))
        else:
            tokens.append(("LETTER", token))
        i = m.end()
    return tokens


def parse(expression):
    """Return an AST: nested tuples, e.g. ("AND", ("OR", "A", "B"), "C")."""
    tokens = tokenize(expression)
    if not tokens:
        raise LogicError("Empty expression.")
    pos = [0]

    def peek():
        return tokens[pos[0]][0] if pos[0] < len(tokens) else None

    def next_token():
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_expr():
        node = parse_term()
        while peek() == "OR":
            next_token()
            node = ("OR", node, parse_term())
        return node

    def parse_term():
        node = parse_factor()
        while peek() == "AND":
            next_token()
            node = ("AND", node, parse_factor())
        return node

    def parse_factor():
        tok_type = peek()
        if tok_type == "NOT":
            next_token()
            return ("NOT", parse_factor())
        if tok_type == "(":
            next_token()
            node = parse_expr()
            if peek() != ")":
                raise LogicError("Missing closing parenthesis.")
            next_token()
            return node
        if tok_type == "LETTER":
            return next_token()[1]
        raise LogicError("Unexpected token: %s" % (tok_type or "end"))

    ast = parse_expr()
    if pos[0] != len(tokens):
        raise LogicError("Unexpected trailing tokens.")
    return ast


def letters_used(ast):
    found = []
    if isinstance(ast, str):
        return [ast]
    for part in ast[1:]:
        found.extend(letters_used(part))
    return found


def evaluate(ast, values):
    if isinstance(ast, str):
        return bool(values.get(ast, False))
    op = ast[0]
    if op == "NOT":
        return not evaluate(ast[1], values)
    if op == "AND":
        return evaluate(ast[1], values) and evaluate(ast[2], values)
    if op == "OR":
        return evaluate(ast[1], values) or evaluate(ast[2], values)
    raise LogicError("Unknown operator: %r" % op)


def compile_expression(expression):
    """Parse and return the AST; raises LogicError on invalid input."""
    return parse(expression)
