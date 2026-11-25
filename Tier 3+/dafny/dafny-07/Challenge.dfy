module Challenge {
  datatype Request = P | Q
  datatype Mat = Mat(m00: int, m01: int, m02: int, m10: int, m11: int, m12: int, m20: int, m21: int, m22: int)
  datatype Witness = Witness(u: Mat, ui: Mat, v: Mat, vi: Mat, d1: int, d2: int, d3: int)

  function Input(r: Request): Mat {
    if r == P then Mat(786, -1884, -156, -318, 762, 62, -600, 1440, 126)
    else Mat(-468, 333, -18, 201, -141, 6, -759, 534, -24)
  }
  function I(): Mat { Mat(1, 0, 0, 0, 1, 0, 0, 0, 1) }
  opaque function Product(a: Mat, b: Mat): Mat {
    Mat(a.m00*b.m00 + a.m01*b.m10 + a.m02*b.m20,
      a.m00*b.m01 + a.m01*b.m11 + a.m02*b.m21,
      a.m00*b.m02 + a.m01*b.m12 + a.m02*b.m22,
      a.m10*b.m00 + a.m11*b.m10 + a.m12*b.m20,
      a.m10*b.m01 + a.m11*b.m11 + a.m12*b.m21,
      a.m10*b.m02 + a.m11*b.m12 + a.m12*b.m22,
      a.m20*b.m00 + a.m21*b.m10 + a.m22*b.m20,
      a.m20*b.m01 + a.m21*b.m11 + a.m22*b.m21,
      a.m20*b.m02 + a.m21*b.m12 + a.m22*b.m22)
  }
  predicate Inverse(a: Mat, b: Mat) { Product(a,b) == I() && Product(b,a) == I() }
  predicate Valid(r: Request, w: Witness) {
    0 < w.d1 && 0 < w.d2 && 0 <= w.d3 &&
    w.d2 % w.d1 == 0 && w.d3 % w.d2 == 0 &&
    Inverse(w.u,w.ui) && Inverse(w.v,w.vi) &&
    Product(Product(w.u,Input(r)),w.v) == Mat(w.d1,0,0, 0,w.d2,0, 0,0,w.d3)
  }

  trait {:termination false} Candidate {
    function Decompose(r: Request): Witness
    ghost method Correct(r: Request)
      ensures Valid(r,Decompose(r))
  }
}
