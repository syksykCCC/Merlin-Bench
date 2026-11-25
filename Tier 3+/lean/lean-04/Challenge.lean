import AMBenchPrelude
namespace Challenge
inductive Ty where
  | base
  | arr (domain codomain : Ty)
inductive Term where
  | var (index : Nat)
  | unit
  | lam (domain : Ty) (body : Term)
  | app (function argument : Term)
abbrev Context := Nat → Option Ty
def empty : Context := fun _ => none
def extend (Γ : Context) (A : Ty) : Context
  | 0 => some A
  | n+1 => Γ n

def up (r : Nat → Nat) : Nat → Nat
  | 0 => 0
  | n+1 => r n + 1

def rename (r : Nat → Nat) : Term → Term
  | .var n => .var (r n)
  | .unit => .unit
  | .lam A body => .lam A (rename (up r) body)
  | .app f a => .app (rename r f) (rename r a)

def lift (σ : Nat → Term) : Nat → Term
  | 0 => .var 0
  | n+1 => rename Nat.succ (σ n)

def subst (σ : Nat → Term) : Term → Term
  | .var n => σ n
  | .unit => .unit
  | .lam A body => .lam A (subst (lift σ) body)
  | .app f a => .app (subst σ f) (subst σ a)

def single (v : Term) : Nat → Term
  | 0 => v
  | n+1 => .var n

inductive Typing : Context → Term → Ty → Prop where
  | var {Γ n A} : Γ n = some A → Typing Γ (.var n) A
  | unit {Γ} : Typing Γ .unit .base
  | lam {Γ A body B} : Typing (extend Γ A) body B → Typing Γ (.lam A body) (.arr A B)
  | app {Γ f a A B} : Typing Γ f (.arr A B) → Typing Γ a A → Typing Γ (.app f a) B

inductive Value : Term → Prop where
  | unit : Value .unit
  | lam {A body} : Value (.lam A body)

inductive Step : Term → Term → Prop where
  | beta {A body v} : Value v → Step (.app (.lam A body) v) (subst (single v) body)
  | appLeft {f f' a} : Step f f' → Step (.app f a) (.app f' a)
  | appRight {f a a'} : Value f → Step a a' → Step (.app f a) (.app f a')

def Target : Prop :=
  (∀ Γ t t' A, Typing Γ t A → Step t t' → Typing Γ t' A) ∧
  (∀ t A, Typing empty t A → Value t ∨ ∃ t', Step t t')
end Challenge
