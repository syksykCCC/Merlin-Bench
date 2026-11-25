import AMBenchPrelude
namespace Challenge
-- Constructive arithmetic interface; no tree-correctness lemmas are supplied.
theorem mul_assoc_free (a b c : Nat) : (a * b) * c = a * (b * c) := by
  induction c with
  | zero => rfl
  | succ c ih =>
    change (a * b) * c + a * b = a * (b * c + b)
    exact Eq.trans (congrArg (fun z => z + a * b) ih) (Eq.symm (Nat.mul_add a (b * c) b))
abbrev Affine := Nat × Nat
def act (f : Affine) (x : Nat) : Nat := f.1 * x + f.2
def compose (f g : Affine) : Affine := (f.1 * g.1, f.1 * g.2 + f.2)
def identity : Affine := (1, 0)

inductive Eager where
  | leaf (value : Nat)
  | node (left right : Eager)
inductive Lazy where
  | leaf (value : Nat)
  | node (tag : Affine) (cached : Nat) (left right : Lazy)

def leaves : Eager → Nat
  | .leaf _ => 1
  | .node l r => leaves l + leaves r
def total : Eager → Nat
  | .leaf v => v
  | .node l r => total l + total r
def map (f : Affine) : Eager → Eager
  | .leaf v => .leaf (act f v)
  | .node l r => .node (map f l) (map f r)
def count : Lazy → Nat
  | .leaf _ => 1
  | .node _ _ l r => count l + count r
def cached : Lazy → Nat
  | .leaf v => v
  | .node _ s _ _ => s
def apply (f : Affine) : Lazy → Lazy
  | .leaf v => .leaf (act f v)
  | .node tag s l r => .node (compose f tag) (f.1 * s + f.2 * (count l + count r)) l r
def join (l r : Lazy) : Lazy := .node identity (cached l + cached r) l r
def push : Lazy → Lazy
  | .leaf v => .leaf v
  | .node tag s l r => .node identity s (apply tag l) (apply tag r)
def build : Eager → Lazy
  | .leaf v => .leaf v
  | .node l r => join (build l) (build r)

def update : List Bool → Affine → Lazy → Lazy
  | [], f, t => apply f t
  | direction :: path, f, t => match push t with
    | .leaf v => .leaf (act f v)
    | .node _ _ l r =>
      if direction then join l (update path f r) else join (update path f l) r
def eagerUpdate : List Bool → Affine → Eager → Eager
  | [], f, t => map f t
  | direction :: path, f, .leaf v => .leaf (act f v)
  | direction :: path, f, .node l r =>
    if direction then .node l (eagerUpdate path f r) else .node (eagerUpdate path f l) r
def query : List Bool → Lazy → Nat
  | [], t => cached t
  | direction :: path, t => match push t with
    | .leaf v => v
    | .node _ _ l r => if direction then query path r else query path l
def eagerQuery : List Bool → Eager → Nat
  | [], t => total t
  | direction :: path, .leaf v => v
  | direction :: path, .node l r => if direction then eagerQuery path r else eagerQuery path l
abbrev Update := List Bool × Affine
def run : List Update → Lazy → Lazy
  | [], t => t
  | command :: rest, t => run rest (update command.1 command.2 t)
def eagerRun : List Update → Eager → Eager
  | [], t => t
  | command :: rest, t => eagerRun rest (eagerUpdate command.1 command.2 t)

def Target : Prop := ∀ initial : Eager, ∀ commands : List Update, ∀ path : List Bool,
  query path (run commands (build initial)) = eagerQuery path (eagerRun commands initial)
end Challenge
