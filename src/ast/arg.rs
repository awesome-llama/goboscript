use logos::Span;

use super::type_::Type;
use crate::misc::SmolStr;

#[derive(Debug)]
pub struct Arg {
    pub name: SmolStr,
    pub span: Span,
    pub type_: Type,
    pub is_used: bool,
}

impl Arg {
    pub fn new(name: SmolStr, span: Span, type_: Type) -> Self {
        Self {
            name,
            span,
            type_,
            is_used: false,
        }
    }
}
