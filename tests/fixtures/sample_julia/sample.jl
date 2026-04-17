"""Sample Julia file for parser tests."""

module SampleModule

import LinearAlgebra
using Statistics

const MAX_SIZE = 1000
const VERSION = "1.0.0"

abstract type Shape end

struct Circle <: Shape
    radius::Float64
end

struct Rectangle <: Shape
    width::Float64
    height::Float64
end

# Compute the area of a circle
function area(c::Circle)
    return pi * c.radius^2
end

# Compute the area of a rectangle
function area(r::Rectangle)
    return r.width * r.height
end

function greet(name::String)
    println("Hello, $name!")
    return "Hello, $name!"
end

macro assert_positive(x)
    return :($x > 0 || error("Expected positive: ", $x))
end

end
