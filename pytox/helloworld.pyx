cdef extern from "tox/tox.h":

  struct Tox_Options
  ctypedef struct Tox

  ctypedef enum Tox_Err_Options_New:
    TOX_ERR_OPTIONS_NEW_OK,
    TOX_ERR_OPTIONS_NEW_MALLOC

  ctypedef enum Tox_Err_New:
    TOX_ERR_NEW_OK,
    TOX_ERR_NEW_NULL,
    TOX_ERR_NEW_MALLOC,
    TOX_ERR_NEW_PORT_ALLOC,
    TOX_ERR_NEW_PROXY_BAD_TYPE,
    TOX_ERR_NEW_PROXY_BAD_HOST,
    TOX_ERR_NEW_PROXY_BAD_PORT,
    TOX_ERR_NEW_PROXY_NOT_FOUND,
    TOX_ERR_NEW_LOAD_ENCRYPTED,
    TOX_ERR_NEW_LOAD_BAD_FORMAT

  Tox_Options *tox_options_new(Tox_Err_Options_New *err)
  Tox *tox_new(Tox_Options *options, Tox_Err_New *error)
  tox_kill(Tox *tox)

cdef Tox_Err_Options_New err
cdef Tox_Options *opts = tox_options_new(&err)
print("Hello World")
