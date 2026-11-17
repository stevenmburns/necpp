/* msvc_compat.h: force-included (/FImsvc_compat.h) in the MSVC build of the
   nec2++ command line, as python-necpp's PyNEC/msvc_compat.h is in the
   Windows wheels. necpp marks some thread-locals with the GCC-only
   __attribute__((tls_model("initial-exec"))), a pure optimisation hint;
   MSVC has no __attribute__, so it expands to nothing. */
#ifndef NECPP_CLI_MSVC_COMPAT_H
#define NECPP_CLI_MSVC_COMPAT_H
#if defined(_MSC_VER) && !defined(__attribute__)
#define __attribute__(x)
#endif
#endif
