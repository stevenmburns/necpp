/*
  Copyright (C) 2004-2015  Timothy C.A. Molteno
  
  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
  
  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
*/
#ifndef __c_ggrid__
#define __c_ggrid__

#include "math_util.h"
#include "common.h"
#include "misc.h"
#include "c_evlcom.h"

using namespace std;


/**
  This class was the old FORTRAN common block 'ggrid'.
  It now contains the ground grid, and methods to do the
  Sommerfeld stuff.
*/
class c_ggrid
{
public:
  static int m_nxa[3], m_nya[3];
  static nec_float m_dxa[3], m_dya[3];
  static nec_float m_xsa[3], m_ysa[3];
  
  nec_complex m_epscf;
  complex_array m_ar1, m_ar2, m_ar3;
  
  c_evlcom m_evlcom;

  c_ggrid() {
    reset_interpolation();
  }

  void initialize()  {
    m_ar1.resize(11*10*4);
    m_ar2.resize(17*5*4);
    m_ar3.resize(9*8*4);
  }

  void interpolate( nec_float x, nec_float y,
    nec_complex *f1, nec_complex *f2,
    nec_complex *f3, nec_complex *f4 );

  void sommerfeld( nec_float epr, nec_float sig, nec_float wavelength );

private:
  /* Interpolation cell cache for interpolate() — was function-local
     static (Fortran SAVE) state. Made per-instance and reset whenever
     sommerfeld() fills a new grid, so coefficients computed against one
     grid can never be reused against another (a new frequency or ground
     in the same process). */
  void reset_interpolation() {
    m_ix = 0; m_iy = 0;
    m_ixs = -10; m_iys = -10; m_igrs = -10;
    m_ixeg = 0; m_iyeg = 0;
    m_nxm2 = 0; m_nym2 = 0; m_nxms = 0; m_nyms = 0;
    m_nd = 0; m_ndp = 0;
    m_dx = 1.; m_dy = 1.; m_xs = 0.; m_ys = 0.;
    m_xz = 0.; m_yz = 0.;
  }

  int m_ix, m_iy, m_ixs, m_iys, m_igrs, m_ixeg, m_iyeg;
  int m_nxm2, m_nym2, m_nxms, m_nyms, m_nd, m_ndp;
  nec_float m_dx, m_dy, m_xs, m_ys, m_xz, m_yz;
  nec_complex m_a[4][4], m_b[4][4], m_c[4][4], m_d[4][4];
};

class c_ground_wave
{
public:
  /* common  /gwav/ */
  nec_float r1, r2, zmh, zph;
  nec_complex u, u2, xx1, xx2;
  
  void set_u(nec_complex in_u)  {
    u = in_u;
    u2 = u * u;
  }
};

void gwave( nec_complex& erv, nec_complex& ezv,
  nec_complex& erh, nec_complex& ezh, nec_complex& eph,
  c_ground_wave& ground_wave);


#endif
