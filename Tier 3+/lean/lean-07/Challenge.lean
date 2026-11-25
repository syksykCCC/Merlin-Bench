import Init
namespace Challenge
inductive Ty where | base | arr (domain codomain : Ty)
inductive Term where
  | var : Nat → Term
  | num : Nat → Term
  | lam : Term → Term
  | app : Term → Term → Term
inductive Val where
  | num : Nat → Val
  | clo : Term → List Val → Val
abbrev Env := List Val
inductive Typing : List Ty → Term → Ty → Prop where
  | var {Γ n A} : Γ[n]? = some A → Typing Γ (.var n) A
  | num {Γ n} : Typing Γ (.num n) .base
  | lam {Γ body A B} : Typing (A :: Γ) body B → Typing Γ (.lam body) (.arr A B)
  | app {Γ f a A B} : Typing Γ f (.arr A B) → Typing Γ a A → Typing Γ (.app f a) B
mutual
inductive ValTyped : Val → Ty → Prop where
  | num {n} : ValTyped (.num n) .base
  | clo {body ρ Γ A B} : Typing (A :: Γ) body B → EnvTyped ρ Γ → ValTyped (.clo body ρ) (.arr A B)
inductive EnvTyped : Env → List Ty → Prop where
  | nil : EnvTyped [] []
  | cons {v ρ A Γ} : ValTyped v A → EnvTyped ρ Γ → EnvTyped (v :: ρ) (A :: Γ)
end
inductive Frame where
  | arg : Term → Env → Frame
  | call : Term → Env → Frame
inductive FrameTyped : Frame → Ty → Ty → Prop where
  | arg {a ρ Γ A B} : Typing Γ a A → EnvTyped ρ Γ → FrameTyped (.arg a ρ) (.arr A B) B
  | call {body ρ Γ A B} : Typing (A :: Γ) body B → EnvTyped ρ Γ → FrameTyped (.call body ρ) A B
inductive StackTyped : List Frame → Ty → Ty → Prop where
  | nil {A} : StackTyped [] A A
  | cons {frame k A B C} : FrameTyped frame A B → StackTyped k B C → StackTyped (frame :: k) A C
inductive State where
  | eval : Term → Env → List Frame → State
  | ret : Val → List Frame → State
inductive StateTyped : State → Ty → Prop where
  | eval {Γ t A ρ k R} : Typing Γ t A → EnvTyped ρ Γ → StackTyped k A R → StateTyped (.eval t ρ k) R
  | ret {v A k R} : ValTyped v A → StackTyped k A R → StateTyped (.ret v k) R
inductive Step : State → State → Prop where
  | var {ρ n v k} : ρ[n]? = some v → Step (.eval (.var n) ρ k) (.ret v k)
  | num {ρ n k} : Step (.eval (.num n) ρ k) (.ret (.num n) k)
  | lam {ρ body k} : Step (.eval (.lam body) ρ k) (.ret (.clo body ρ) k)
  | app {ρ f a k} : Step (.eval (.app f a) ρ k) (.eval f ρ (.arg a ρ :: k))
  | argument {body saved a ρ k} : Step (.ret (.clo body saved) (.arg a ρ :: k)) (.eval a ρ (.call body saved :: k))
  | apply {v body saved k} : Step (.ret v (.call body saved :: k)) (.eval body (v :: saved) k)
def Final : State → Prop
  | .ret _ [] => True
  | _ => False
def Target : Prop :=
  (∀ s s' R, StateTyped s R → Step s s' → StateTyped s' R) ∧
  (∀ s R, StateTyped s R → Final s ∨ ∃ s', Step s s')
end Challenge
