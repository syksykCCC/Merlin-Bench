import Init
namespace Challenge
inductive Term where
  | var (index : Nat)
  | lam (body : Term)
  | app (function argument : Term)
def up (r : Nat → Nat) : Nat → Nat
  | 0 => 0
  | n+1 => r n + 1
def rename (r : Nat → Nat) : Term → Term
  | .var n => .var (r n)
  | .lam b => .lam (rename (up r) b)
  | .app f a => .app (rename r f) (rename r a)
def lift (σ : Nat → Term) : Nat → Term
  | 0 => .var 0
  | n+1 => rename Nat.succ (σ n)
def subst (σ : Nat → Term) : Term → Term
  | .var n => σ n
  | .lam b => .lam (subst (lift σ) b)
  | .app f a => .app (subst σ f) (subst σ a)
def single (a : Term) : Nat → Term
  | 0 => a
  | n+1 => .var n
inductive Parallel : Term → Term → Prop where
  | var (n) : Parallel (.var n) (.var n)
  | lam {b b'} : Parallel b b' → Parallel (.lam b) (.lam b')
  | app {f f' a a'} : Parallel f f' → Parallel a a' → Parallel (.app f a) (.app f' a')
  | beta {b b' a a'} : Parallel b b' → Parallel a a' → Parallel (.app (.lam b) a) (subst (single a') b')
def Target : Prop := ∀ t u v, Parallel t u → Parallel t v → ∃ w, Parallel u w ∧ Parallel v w
end Challenge
