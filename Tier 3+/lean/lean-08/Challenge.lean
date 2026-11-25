import Init
namespace Challenge

inductive Term where
  | var : Nat → Term
  | num : Nat → Term
  | lam : Term → Term
  | app : Term → Term → Term

inductive Val where
  | num : Nat → Val
  | clo : Term → List Val → Val

abbrev Env := List Val

inductive Eval : Env → Term → Val → Prop where
  | var {ρ n v} : ρ[n]? = some v → Eval ρ (.var n) v
  | num {ρ n} : Eval ρ (.num n) (.num n)
  | lam {ρ body} : Eval ρ (.lam body) (.clo body ρ)
  | app {ρ f a body saved v result} :
      Eval ρ f (.clo body saved) → Eval ρ a v → Eval (v :: saved) body result →
      Eval ρ (.app f a) result

def evaluate : Nat → Env → Term → Option Val
  | 0, _, _ => none
  | fuel+1, ρ, .var n => ρ[n]?
  | fuel+1, _, .num n => some (.num n)
  | fuel+1, ρ, .lam body => some (.clo body ρ)
  | fuel+1, ρ, .app f a =>
    match evaluate fuel ρ f with
    | some (.clo body saved) =>
      match evaluate fuel ρ a with
      | some v => evaluate fuel (v :: saved) body
      | none => none
    | _ => none

def Target : Prop :=
  (∀ fuel ρ t v, evaluate fuel ρ t = some v → Eval ρ t v) ∧
  (∀ ρ t v, Eval ρ t v → ∃ bound, ∀ fuel, bound ≤ fuel → evaluate fuel ρ t = some v) ∧
  (∀ fuel more ρ t v, fuel ≤ more → evaluate fuel ρ t = some v → evaluate more ρ t = some v)
end Challenge
