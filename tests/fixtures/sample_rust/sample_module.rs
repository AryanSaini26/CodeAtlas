use std::fmt;
use std::collections::HashMap;

const MAX_USERS: u32 = 100;

static APP_NAME: &str = "CodeAtlas";

/// A user in the system
pub struct User {
    pub name: String,
    pub age: u32,
}

/// Defines greeting behavior
pub trait Greeter {
    fn greet(&self) -> String;
}

impl Greeter for User {
    fn greet(&self) -> String {
        format!("Hello, I am {}", self.name)
    }
}

pub enum Color {
    Red,
    Green,
    Blue,
}

type UserId = u64;

mod utils;

/// Creates a new user
pub fn create_user(name: &str, age: u32) -> User {
    println!("Creating user: {}", name);
    User {
        name: name.to_string(),
        age,
    }
}

impl User {
    pub fn new(name: String, age: u32) -> Self {
        Self { name, age }
    }

    pub fn display(&self) -> String {
        fmt::format(format_args!("{} ({})", self.name, self.age))
    }
}

impl fmt::Display for User {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "{} (age {})", self.name, self.age)
    }
}
