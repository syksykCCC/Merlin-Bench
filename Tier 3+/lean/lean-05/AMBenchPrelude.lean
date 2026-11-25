import Init

namespace AMBenchPrelude

def powMod (base exponent modulus : Nat) : Nat :=
  match exponent with
  | 0 => 1 % modulus
  | n + 1 => (powMod base n modulus * (base % modulus)) % modulus

def evalPolyMod (coefficients : List Nat) (x modulus : Nat) : Nat :=
  match coefficients with
  | [] => 0
  | coefficient :: rest =>
      (coefficient + x * evalPolyMod rest x modulus) % modulus

def absDiff (a b : Nat) : Nat :=
  if a <= b then b - a else a - b

end AMBenchPrelude
