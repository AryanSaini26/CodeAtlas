require "json"
require_relative "./models"

# Maximum number of retries
MAX_RETRIES = 3

# Utility helpers
module Utils
  # Formats a message
  def self.format_message(msg)
    "[INFO] #{msg}"
  end
end

# Base class for all animals
class Animal
  # Creates a new animal
  def initialize(name, species)
    @name = name
    @species = species
  end

  # Returns the animal's name
  def name
    @name
  end

  def speak
    puts Utils.format_message("...")
  end

  # Factory method
  def self.create(name, species)
    new(name, species)
  end
end

# A domesticated animal
class Dog < Animal
  def speak
    bark()
    puts "Woof!"
  end

  def fetch(item)
    grab(item)
  end

  private

  def bark
    puts "Bark!"
  end
end

# Top-level helper function
def process_animals(animals)
  animals.each do |a|
    a.speak
  end
end
