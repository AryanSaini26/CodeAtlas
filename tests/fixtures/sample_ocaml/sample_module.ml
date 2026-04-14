open Printf

let pi = 3.14159

type color = Red | Green | Blue

type point = {
  x: float;
  y: float;
}

module Math = struct
  let add a b = a + b
  let multiply a b = a * b
end

let greet name =
  printf "Hello, %s!\n" name

let add x y = x + y

let rec factorial n =
  if n <= 1 then 1
  else n * factorial (n - 1)

let compute a b =
  let s = add a b in
  let p = factorial s in
  p
