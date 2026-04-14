import Foundation
import UIKit

// Type alias for a completion handler
typealias Completion = (String) -> Void

// Protocol for drawable objects
protocol Drawable {
    /// Draw the object
    func draw()
}

// Protocol for serializable objects
protocol Serializable {
    func serialize() -> String
}

/// Base shape class
class Shape: Drawable {
    let name: String

    /// Initialise with a name
    init(name: String) {
        self.name = name
    }

    /// Draw the shape
    func draw() {
        formatName()
    }

    /// Factory method
    static func create(name: String) -> Shape {
        return Shape(name: name)
    }

    private func formatName() -> String {
        return name.uppercased()
    }
}

/// A circle, subclassing Shape
class Circle: Shape {
    var radius: Double

    init(name: String, radius: Double) {
        self.radius = radius
        super.init(name: name)
    }

    override func draw() {
        computeArea()
    }

    func computeArea() -> Double {
        return 3.14159 * radius * radius
    }
}

/// Top-level utility function
func greet(name: String) -> String {
    return "Hello, \(name)!"
}

/// Compute sum
func add(a: Int, b: Int) -> Int {
    return a + b
}
