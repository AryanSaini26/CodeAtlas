module SampleModule where

import Data.List (sort, nub)
import Data.Maybe (fromMaybe)

-- | Core animal type
data Animal = Cat | Dog | Fish

-- | Direction enumeration
data Direction = North | South | East | West

-- | Type alias for a name string
type Name = String

-- | Newtype wrapper for identifiers
newtype UserId = UserId { getId :: Int }

-- | Type class for things that can speak
class Speakable a where
    speak :: a -> String

-- | Format a greeting
greet :: Name -> String
greet name = "Hello, " ++ name ++ "!"

-- | Add two integers
add :: Int -> Int -> Int
add x y = x + y

-- | Process a list of names
processNames :: [Name] -> [String]
processNames names = map greet (sort names)

-- | Entry point
main :: IO ()
main = do
    putStrLn (greet "World")
    print (add 1 2)
    processNames ["Alice", "Bob"]
