const std = @import("std");
const math = @import("math.zig");

pub const MAX_SIZE: usize = 1024;

const Color = enum { Red, Green, Blue };

const Point = struct {
    x: f64,
    y: f64,
};

const Shape = union {
    circle: f64,
    rect: Point,
};

pub fn add(a: i32, b: i32) i32 {
    return a + b;
}

pub fn multiply(a: i32, b: i32) i32 {
    return a * b;
}

fn compute(a: i32, b: i32) i32 {
    const sum = add(a, b);
    const product = multiply(a, b);
    return sum + product;
}
