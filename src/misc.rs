use core::fmt;
use std::{cell::RefCell, io, rc::Rc};

pub fn write_comma_io<T>(mut file: T, comma: &mut bool) -> io::Result<()>
where T: io::Write {
    if *comma {
        file.write_all(b",")?;
    }
    *comma = true;
    Ok(())
}

pub fn write_comma_fmt<T>(mut file: T, comma: &mut bool) -> fmt::Result
where T: fmt::Write {
    if *comma {
        file.write_str(",")?;
    }
    *comma = true;
    Ok(())
}

pub type Rrc<T> = Rc<RefCell<T>>;

pub fn rrc<T>(value: T) -> Rrc<T> {
    Rc::new(RefCell::new(value))
}
