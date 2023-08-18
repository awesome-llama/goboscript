import math
from difflib import get_close_matches
from itertools import chain
from typing import Any, Iterator, cast

from gdefinitionvisitor import gDefinitionVisitor, gFunction
from gerror import gFileError, gTokenError
from gparser import literal
from lark.lexer import Token
from lark.visitors import Transformer
from lib import num_plural, number
from sb3 import (
    gArgument,
    gBlock,
    gHatBlock,
    gInputType,
    gList,
    gProcCall,
    gProcDef,
    gStack,
    gVariable,
)
from sb3.gblockfactory import reporter_prototypes, statement_prototypes


def coerce_condition(input: gInputType) -> gBlock:
    if isinstance(input, gBlock) and input.opcode in (
        "operator_equals",
        "operator_lt",
        "operator_gt",
        "operator_and",
        "operator_or",
        "operator_contains",
        "sensing_touchingcolor",
        "sensing_coloristouchingcolor",
        "sensing_keypressed",
        "data_listcontainsitem",
    ):
        return input
    elif isinstance(input, gList):
        return gBlock(
            "operator_not",
            {
                "OPERAND": gBlock(
                    "operator_equals",
                    {
                        "OPERAND1": "0",
                        "OPERAND2": gBlock("data_lengthoflist", {}, {"LIST": input}),
                    },
                    {},
                )
            },
            {},
        )
    else:
        return gBlock(
            "operator_not",
            {
                "OPERAND": gBlock(
                    "operator_equals",
                    {"OPERAND1": "0", "OPERAND2": input},
                    {},
                    comment="auto-generated",
                )
            },
            {},
        )


def mkelif(
    rest: Iterator[tuple[gInputType, gStack]],
    this: tuple[gInputType, gStack] | None = None,
    _else: gStack | None = None,
) -> gBlock:
    if this is None:
        this = next(rest)
    try:
        nxt = next(rest)
    except StopIteration:
        if _else is None:
            return gBlock(
                "control_if",
                {
                    "CONDITION": coerce_condition(this[0]),
                    "SUBSTACK": coerce_condition(this[1]),
                },
                {},
            )
        else:
            return gBlock(
                "control_if_else",
                {
                    "CONDITION": coerce_condition(this[0]),
                    "SUBSTACK": coerce_condition(this[1]),
                    "SUBSTACK2": _else,
                },
                {},
            )
    return gBlock(
        "control_if_else",
        {
            "CONDITION": coerce_condition(this[0]),
            "SUBSTACK": coerce_condition(this[1]),
            "SUBSTACK2": gStack([mkelif(rest, nxt, _else)]),
        },
        {},
    )


class gBlockTransformer(Transformer[Token, gBlock]):
    def __init__(
        self,
        gdefinitionvisitor: gDefinitionVisitor,
        prototype: gFunction | None = None,
    ):
        super().__init__(True)
        self.gdefinitionvisitor = gdefinitionvisitor
        self.sprite = gdefinitionvisitor.sprite
        self.prototype = prototype

    def STRING(self, token: Token):
        return literal(token)

    NUMBER = STRING
    FLOAT = STRING

    def start(self, args: tuple[gBlock]):
        return args[0]

    def expr(self, args: tuple[gInputType]):
        return args[0]

    def argument(self, args: tuple[Token]):
        if self.prototype:
            argument = literal(args[0])
            if argument not in self.prototype.arguments:
                matches = get_close_matches(argument, self.prototype.arguments)
                raise gTokenError(
                    "Undefined function argument",
                    args[0],
                    f"Did you mean `${matches[0]}`?" if matches else None,
                )
            return gArgument(argument)
        else:
            raise gTokenError(
                "Argument reporter used outsite function declaration", args[0]
            )

    def declr_function(self, args: list[Any], warp: bool = True) -> gProcDef:
        name: Token = args[0]
        arguments: list[Token] = args[1:-1]
        if arguments == [None]:
            arguments = []
        stack: gStack = args[-1]
        return gProcDef(name, arguments, warp, stack)

    def declr_function_nowarp(self, args: list[Any]) -> gProcDef:
        return self.declr_function(args, False)

    def stack(self, args: list[gBlock]) -> gStack:
        stack = gStack(args)
        for i, block in enumerate(stack):
            if block.opcode == "control_forever" and (i + 1) != len(stack):
                raise gFileError(
                    "forever cannot be precceded by any statements"
                )  # FIXME: switch to gTokenError but cannot because
        return stack

    def block(self, args: list[Any]) -> gBlock:
        opcode: Token = args[0]
        arguments: list[gInputType] = args[1:-1]
        comment: str | None = literal(args[-1]) if args[-1] else None
        if arguments == [None]:
            arguments = []
        if opcode in statement_prototypes:
            prototype = statement_prototypes[opcode]
            if len(arguments) > len(prototype.arguments):
                raise gTokenError(
                    "Too many arguments for statement",
                    opcode,
                    f"Expected {num_plural(len(prototype.arguments), ' argument')}",
                )
            if len(arguments) < len(prototype.arguments):
                raise gTokenError(
                    "Missing arguments for statement",
                    opcode,
                    f"Missing {', '.join(prototype.arguments[len(arguments):])}",
                )
            return gBlock.from_prototype(prototype, arguments, comment)
        elif opcode in self.gdefinitionvisitor.functions.keys():
            prototype = self.gdefinitionvisitor.functions[opcode]
            if len(arguments) > len(prototype.arguments):
                raise gTokenError(
                    "Too many arguments for function",
                    opcode,
                    f"Expected {num_plural(len(prototype), ' argument')}",
                )
            if len(arguments) < len(prototype.arguments):
                raise gTokenError(
                    "Missing arguments for function",
                    opcode,
                    f"Missing {', '.join(prototype.arguments[len(arguments):])}",
                )
            return gProcCall(
                opcode,
                dict(zip(prototype.arguments, arguments)),
                prototype.warp,
                comment,
                prototype.proccode,
            )
        else:
            matches = get_close_matches(
                args[0],
                chain(
                    statement_prototypes.keys(),
                    self.gdefinitionvisitor.functions.keys(),
                ),
            )
            raise gTokenError(
                f"Undefined statement or function `{opcode}`",
                args[0],
                (f"Did you mean `{matches[0]}`?\n" if matches else "")
                + "Read --doc statements for available statements",
            )

    def reporter(self, args: list[Any]) -> gInputType:
        opcode: Token = args[0]
        arguments: list[gInputType] = args[1:]
        if arguments == [None]:
            arguments = []
        if opcode not in reporter_prototypes:
            matches = get_close_matches(str(args[0]), reporter_prototypes.keys())
            raise gTokenError(
                f"Undefined reporter `{opcode}`",
                args[0],
                (f"Did you mean `{matches[0]}`?\n" if matches else "")
                + "Read --doc reporters for available reporters",
            )
        prototype = reporter_prototypes[opcode]
        if len(arguments) > len(prototype.arguments):
            raise gTokenError(
                "Too many arguments for reporter",
                opcode,
                f"Expected {num_plural(len(prototype.arguments), ' argument')}",
            )
        if len(arguments) < len(prototype.arguments):
            raise gTokenError(
                "Missing arguments for reporter",
                opcode,
                f"Missing {', '.join(prototype.arguments[len(arguments):])}",
            )
        if (
            prototype.opcode == "operator_mathop.OPERATOR=sqrt"
            and type(arguments[0]) is str
        ):
            return str(math.sqrt(number(arguments[0])))
        return gBlock.from_prototype(prototype, arguments)

    def add(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            try:
                return str(number(args[0]) + number(args[1]))
            except ValueError:
                pass
        return gBlock.from_prototype(reporter_prototypes["add"], args)

    def sub(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            try:
                return str(number(args[0]) - number(args[1]))
            except ValueError:
                pass
        return gBlock.from_prototype(reporter_prototypes["sub"], args)

    def minus(self, args: tuple[gInputType]):
        if type(args[0]) is str:
            if args[0].startswith("-"):
                return args[0].removeprefix("-")
            return "-" + args[0]
        return gBlock.from_prototype(reporter_prototypes["sub"], ["0", args[0]])

    def mul(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            return str(number(args[0]) * number(args[1]))
        return gBlock.from_prototype(reporter_prototypes["mul"], args)

    def div(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            return str(number(args[0]) / number(args[1]))
        return gBlock.from_prototype(reporter_prototypes["div"], args)

    def mod(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            return str(number(args[0]) % number(args[1]))
        return gBlock.from_prototype(reporter_prototypes["mod"], args)

    def join(self, args: list[gInputType]):
        if type(args[0]) is str and type(args[1]) is str:
            return args[0] + args[1]
        return gBlock.from_prototype(reporter_prototypes["join"], args)

    def eq(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["eq"], args)

    def gt(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["gt"], args)

    def lt(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["lt"], args)

    def andop(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["AND"], args)

    def orop(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["OR"], args)

    def notop(self, args: list[gInputType]):
        return gBlock.from_prototype(reporter_prototypes["NOT"], args)

    def block_if(self, args: tuple[gInputType, gStack]):
        return gBlock(
            "control_if",
            {"CONDITION": coerce_condition(args[0]), "SUBSTACK": args[1]},
            {},
        )

    def block_if_else(self, args: tuple[gInputType, gStack, gStack]):
        return gBlock(
            "control_if_else",
            {
                "CONDITION": coerce_condition(args[0]),
                "SUBSTACK": args[1],
                "SUBSTACK2": args[2],
            },
            {},
        )

    def block_if_elif(self, args: list[Any]):
        return mkelif(cast(Any, zip(*[iter(args)] * 2)))

    def block_if_elif_else(self, args: list[Any]):
        return mkelif(cast(Any, zip(*[iter(args[:-1])] * 2)), _else=args[-1])

    def until(self, args: tuple[gInputType, gStack]):
        return gBlock(
            "control_repeat_until",
            {"CONDITION": coerce_condition(args[0]), "SUBSTACK": args[1]},
            {},
        )

    def repeat(self, args: tuple[gInputType, gStack]):
        return gBlock("control_repeat", {"TIMES": args[0], "SUBSTACK": args[1]}, {})

    def forever(self, args: tuple[gStack]):
        return gBlock("control_forever", {"SUBSTACK": args[0]}, {})

    def localvar(self, args: tuple[Token, gInputType]):
        variable = self.get_variable(args[0])
        if not self.prototype:
            raise gTokenError(
                "local variables cannot be used outside of functions",
                args[0],
                help="switch to a non-local variable",
            )
        return gBlock(
            "data_setvariableto",
            {"VALUE": args[1]},
            {"VARIABLE": variable},
        )

    def var(self, args: tuple[Token]):
        return self.get_identifier(args[0])

    def varset(self, args: tuple[Token, gInputType]):
        variable = self.get_variable(args[0])
        return gBlock(
            "data_setvariableto",
            {"VALUE": args[1]},
            {"VARIABLE": variable},
        )

    def varOP(self, opcode: str, args: tuple[Token, gInputType]):
        variable = self.get_variable(args[0])
        return gBlock(
            "data_setvariableto",
            {
                "VALUE": gBlock.from_prototype(
                    reporter_prototypes[opcode], [variable, args[1]]
                )
            },
            {"VARIABLE": variable},
        )

    def varmul(self, args: Any):
        return self.varOP("mul", args)

    def vardiv(self, args: Any):
        return self.varOP("div", args)

    def varmod(self, args: Any):
        return self.varOP("mod", args)

    def varjoin(self, args: Any):
        return self.varOP("join", args)

    def varchange(self, args: tuple[Token, gInputType]):
        variable = self.get_variable(args[0])  # type: ignore
        return gBlock(
            "data_changevariableby",
            {"VALUE": args[1]},
            {"VARIABLE": variable},
        )

    def varsub(self, args: tuple[Token, gInputType]):
        variable = self.get_variable(args[0])  # type: ignore
        return gBlock(
            "data_changevariableby",
            {
                "VALUE": gBlock.from_prototype(
                    reporter_prototypes["sub"], ["0", args[1]]
                )
            },
            {"VARIABLE": variable},
        )

    def get_identifier(self, token: Token):
        name = str(token)

        if self.prototype and name in self.prototype.locals:
            return self.sprite.variables[f"{self.prototype.name}.{name}"]

        if name in self.sprite.variables:
            return self.sprite.variables[name]

        if name in self.sprite.lists:
            return self.sprite.lists[name]

        help = None
        if matches := get_close_matches(name, self.sprite.variables.keys()):
            help = f"Did you mean the variable `{matches[0]}?`"
        elif matches := get_close_matches(name, self.sprite.lists.keys()):
            help = f"Did you mean the list `{matches[0]}?`"
        elif self.prototype:
            if matches := get_close_matches(name, self.prototype.locals):
                help = f"Did you mean the local variable `{matches[0]}?`"

        raise gTokenError(f"Undefined variable or list `{token}`", token, help)

    def listset(self, args: tuple[Any]):
        list_ = self.get_list(args[0])
        return gBlock("data_deletealloflist", {}, {"LIST": list_})

    def listadd(self, args: tuple[Token, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock("data_addtolist", {"ITEM": args[1]}, {"LIST": list_})

    def listdelete(self, args: tuple[Token, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock("data_deleteoflist", {"INDEX": args[1]}, {"LIST": list_})

    def listinsert(self, args: tuple[Token, gInputType, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock(
            "data_insertatlist",
            {"INDEX": args[1], "ITEM": args[2]},
            {"LIST": list_},
        )

    def listreplace(self, args: tuple[Token, gInputType, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock(
            "data_replaceitemoflist",
            {"INDEX": args[1], "ITEM": args[2]},
            {"LIST": list_},
        )

    def listreplaceOP(self, opcode: str, args: tuple[Token, gInputType, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock(
            "data_replaceitemoflist",
            {
                "INDEX": args[1],
                "ITEM": gBlock.from_prototype(
                    reporter_prototypes[opcode],
                    [
                        gBlock(
                            "data_itemoflist",
                            {"INDEX": args[1]},
                            {"LIST": list_},
                        ),
                        args[2],
                    ],
                ),
            },
            {"LIST": list_},
        )

    def listreplaceadd(self, args: Any):
        return self.listreplaceOP("add", args)

    def listreplacesub(self, args: Any):
        return self.listreplaceOP("sub", args)

    def listreplacemul(self, args: Any):
        return self.listreplaceOP("mul", args)

    def listreplacediv(self, args: Any):
        return self.listreplaceOP("div", args)

    def listreplacemod(self, args: Any):
        return self.listreplaceOP("mod", args)

    def listreplacejoin(self, args: Any):
        return self.listreplaceOP("join", args)

    def listshow(self, args: tuple[Token]):
        list_ = self.get_list(args[0])
        return gBlock("data_showlist", {}, {"LIST": list_})

    def listhide(self, args: tuple[Token]):
        list_ = self.get_list(args[0])
        return gBlock("data_hidelist", {}, {"LIST": list_})

    def listitem(self, args: tuple[Token, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock("data_itemoflist", {"INDEX": args[1]}, {"LIST": list_})

    def listindex(self, args: tuple[Token, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock("data_itemnumoflist", {"ITEM": args[1]}, {"LIST": list_})

    def listcontains(self, args: tuple[Token, gInputType]):
        list_ = self.get_list(args[0])
        return gBlock("data_listcontainsitem", {"ITEM": args[1]}, {"LIST": list_})

    def listlength(self, args: tuple[Token]):
        list_ = self.get_list(args[0])
        return gBlock("data_lengthoflist", {}, {"LIST": list_})

    def declr_on(self, args: tuple[Token, gStack]):
        return gHatBlock(
            "event_whenbroadcastreceived",
            {},
            {"BROADCAST_OPTION": gVariable(str(args[0]), args[0])},
            args[1],
        )

    def declr_onkey(self, args: tuple[Token, gStack]):
        return gHatBlock(
            "event_whenkeypressed",
            {},
            {"KEY_OPTION": gVariable(str(args[0]), args[0])},
            args[1],
        )

    def declr_onbackdrop(self, args: tuple[Token, gStack]):
        return gHatBlock(
            "event_whenbackdropswitchesto",
            {},
            {"BACKDROP_OPTION": gVariable(str(args[0]), args[0])},
            args[1],
        )

    def declr_onloudness(self, args: tuple[gInputType, gStack]):
        return gHatBlock(
            "event_whengreaterthan",
            {"VALUE": args[0]},
            {"WHENGREATERTHANMENU": "LOUDNESS"},
            args[1],
        )

    def declr_ontimer(self, args: tuple[gInputType, gStack]):
        return gHatBlock(
            "event_whengreaterthan",
            {"VALUE": args[0]},
            {"WHENGREATERTHANMENU": "TIMER"},
            args[1],
        )

    def declr_onflag(self, args: tuple[gStack]):
        return gHatBlock("event_whenflagclicked", {}, {}, args[0])

    def declr_onclick(self, args: tuple[gStack]):
        return gHatBlock("event_whenthisspriteclicked", {}, {}, args[0])

    def declr_onclone(self, args: tuple[gStack]):
        return gHatBlock("control_start_as_clone", {}, {}, args[0])

    def nop(self, args: tuple[()]):
        return gBlock("control_wait", {"DURATION": "0"}, {})

    def get_variable(self, token: Token):
        if isinstance(token, gVariable):
            return token
        if isinstance(token, gList):
            raise gTokenError("Identifier is not a variable", token.token)

        identifier = self.get_identifier(token)
        if not isinstance(identifier, gVariable):
            raise gTokenError("Identifier is not a variable", token)
        return identifier

    def get_list(self, token: Token):
        if isinstance(token, gList):
            return token
        if isinstance(token, gVariable):
            raise gTokenError("Identifier is not a list", token.token)

        identifier = self.get_identifier(token)
        if not isinstance(identifier, gList):
            raise gTokenError("Identifier is not a list", token)
        return identifier
