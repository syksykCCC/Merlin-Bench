import AMBenchPrelude
namespace Challenge

-- Generic constructive arithmetic, not differentiation-correctness lemmas.
theorem mul_assoc_free (a b c : Nat) : (a * b) * c = a * (b * c) := by
  induction c with
  | zero => rfl
  | succ c ih =>
    change (a * b) * c + a * b = a * (b * c + b)
    exact Eq.trans (congrArg (fun z => z + a * b) ih) (Eq.symm (Nat.mul_add a (b * c) b))

theorem zero_mul_free (b : Nat) : 0 * b = 0 := by
  induction b with
  | zero => rfl
  | succ b ih => exact Eq.trans (Nat.add_zero _) ih

theorem add_mul_free (a b c : Nat) : (a + b) * c = a * c + b * c := by
  induction c with
  | zero => rfl
  | succ c ih =>
    change (a + b) * c + (a + b) = (a * c + a) + (b * c + b)
    exact Eq.trans (congrArg (fun z => z + (a + b)) ih) (Nat.add_add_add_comm _ _ _ _)

-- Intrinsic finite indices use constructors only, avoiding proof-carrying casts.
def Index : Nat → Type
  | 0 => Empty
  | n+1 => Option (Index n)
def Index.zero {n : Nat} : Index (n+1) := none
def Index.succ {n : Nat} (i : Index n) : Index (n+1) := some i
instance {n : Nat} : OfNat (Index (n+1)) 0 := ⟨Index.zero⟩
def Index.cases {n : Nat} {motive : Index (n+1) → Sort u}
    (head : motive .zero) (tail : (i : Index n) → motive (.succ i)) : (i : Index (n+1)) → motive i
  | none => head
  | some i => tail i
def Index.elim0 {α : Sort u} (i : Index 0) : α := Empty.elim i

abbrev Registers (n : Nat) := Index n → Nat
def extend {n : Nat} (head : Nat) (tail : Registers n) : Registers (n+1) := Index.cases head tail
def tail {n : Nat} (v : Registers (n+1)) : Registers n := fun i => v i.succ
def zero {n : Nat} : Registers n := fun _ => 0
def plus {n : Nat} (a b : Registers n) : Registers n := fun i => a i + b i

def basis : {n : Nat} → Index n → Nat → Registers n
  | 0, i, _ => Index.elim0 i
  | n+1, i, seed => Index.cases (motive := fun _ => Registers (n+1)) (extend seed zero) (fun j => extend 0 (basis j seed)) i

def dot : {n : Nat} → Registers n → Registers n → Nat
  | 0, _, _ => 0
  | _+1, a, b => a 0 * b 0 + dot (tail a) (tail b)

-- Destructive point update: all other registers are retained.
def write : {n : Nat} → Registers n → Index n → Nat → Registers n
  | 0, _, i, _ => Index.elim0 i
  | n+1, x, i, value => Index.cases (motive := fun _ => Registers (n+1))
      (extend value (tail x)) (fun j => extend (x 0) (write (tail x) j value)) i

inductive Kind where
  | add
  | mul

structure Assignment (n : Nat) where
  kind : Kind
  destination : Index n
  left : Index n
  right : Index n

structure Entry (n : Nat) where
  instruction : Assignment n
  oldLeft : Nat
  oldRight : Nat

def saved {n : Nat} (op : Assignment n) (x : Registers n) : Entry n :=
  ⟨op, x op.left, x op.right⟩

def primal {n : Nat} (op : Assignment n) (x : Registers n) : Nat :=
  match op.kind with
  | .add => x op.left + x op.right
  | .mul => x op.left * x op.right

def tangent {n : Nat} (op : Assignment n) (x dx : Registers n) : Nat :=
  match op.kind with
  | .add => dx op.left + dx op.right
  | .mul => x op.right * dx op.left + x op.left * dx op.right

def advance {n : Nat} (op : Assignment n) (x : Registers n) : Registers n :=
  write x op.destination (primal op x)

-- Forward pass records operand values BEFORE destructive assignment.
-- The returned log is chronological, oldest instruction first.
def record {n : Nat} : List (Assignment n) → Registers n → Registers n × List (Entry n)
  | [], x => (x, [])
  | op :: ops, x =>
    let result := record ops (advance op x)
    (result.1, saved op x :: result.2)

-- Independent forward directional propagation, with the same primal assignments.
def forward {n : Nat} : List (Assignment n) → Registers n → Registers n → Registers n
  | [], _, dx => dx
  | op :: ops, x, dx =>
    forward ops (advance op x) (write dx op.destination (tangent op x dx))

-- Capture the destination's seed before clearing its overwritten value.
-- Then accumulate BOTH contributions, even when operands/destination alias.
def pull {n : Nat} (entry : Entry n) (adj : Registers n) : Registers n :=
  let op := entry.instruction
  let seed := adj op.destination
  let cleared := write adj op.destination 0
  match op.kind with
  | .add => plus (plus cleared (basis op.left seed)) (basis op.right seed)
  | .mul => plus (plus cleared (basis op.left (seed * entry.oldRight)))
      (basis op.right (seed * entry.oldLeft))

-- Backward execution consumes a log in its GIVEN order, not chronological order.
def backward {n : Nat} : List (Entry n) → Registers n → Registers n
  | [], adj => adj
  | entry :: entries, adj => backward entries (pull entry adj)

def reverse {n : Nat} (ops : List (Assignment n)) (x : Registers n)
    (output : Index n) (seed : Nat) : Registers n :=
  backward (record ops x).2.reverse (basis output seed)

def Target : Prop := ∀ n : Nat, ∀ ops : List (Assignment (n+1)),
  ∀ x dx : Registers (n+1), ∀ output : Index (n+1), ∀ seed : Nat,
    dot (reverse ops x output seed) dx = seed * forward ops x dx output

end Challenge
