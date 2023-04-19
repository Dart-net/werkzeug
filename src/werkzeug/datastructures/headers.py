from __future__ import annotations

import re
import typing as t
import warnings

from .._internal import _missing
from ..exceptions import BadRequestKeyError
from .mixins import ImmutableHeadersMixin
from .structures import iter_multi_items
from .structures import MultiDict


class Headers:
    """An object that stores some headers. It has a dict-like interface,
    but is ordered, can store the same key multiple times, and iterating
    yields ``(key, value)`` pairs instead of only keys.

    This data structure is useful if you want a nicer way to handle WSGI
    headers which are stored as tuples in a list.

    From Werkzeug 0.3 onwards, the :exc:`KeyError` raised by this class is
    also a subclass of the :class:`~exceptions.BadRequest` HTTP exception
    and will render a page for a ``400 BAD REQUEST`` if caught in a
    catch-all for HTTP exceptions.

    Headers is mostly compatible with the Python :class:`wsgiref.headers.Headers`
    class, with the exception of `__getitem__`.  :mod:`wsgiref` will return
    `None` for ``headers['missing']``, whereas :class:`Headers` will raise
    a :class:`KeyError`.

    To create a new ``Headers`` object, pass it a list, dict, or
    other ``Headers`` object with default values. These values are
    validated the same way values added later are.

    :param defaults: The list of default values for the :class:`Headers`.

    .. versionchanged:: 2.1.0
        Default values are validated the same as values added later.

    .. versionchanged:: 0.9
       This data structure now stores unicode values similar to how the
       multi dicts do it.  The main difference is that bytes can be set as
       well which will automatically be latin1 decoded.

    .. versionchanged:: 0.9
       The :meth:`linked` function was removed without replacement as it
       was an API that does not support the changes to the encoding model.
    """

    def __init__(self, defaults=None):
        self._list = []
        if defaults is not None:
            self.extend(defaults)

    def __getitem__(self, key, _get_mode=False):
        if not _get_mode:
            if isinstance(key, int):
                return self._list[key]
            elif isinstance(key, slice):
                return self.__class__(self._list[key])
        if not isinstance(key, str):
            raise BadRequestKeyError(key)
        ikey = key.lower()
        for k, v in self._list:
            if k.lower() == ikey:
                return v
        # micro optimization: if we are in get mode we will catch that
        # exception one stack level down so we can raise a standard
        # key error instead of our special one.
        if _get_mode:
            raise KeyError()
        raise BadRequestKeyError(key)

    def __eq__(self, other):
        def lowered(item):
            return (item[0].lower(),) + item[1:]

        return other.__class__ is self.__class__ and set(
            map(lowered, other._list)
        ) == set(map(lowered, self._list))

    __hash__ = None

    def get(self, key, default=None, type=None, as_bytes=None):
        """Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        >>> d = Headers([('Content-Length', '42')])
        >>> d.get('Content-Length', type=int)
        42

        :param key: The key to be looked up.
        :param default: The default value to be returned if the key can't
                        be looked up.  If not further specified `None` is
                        returned.
        :param type: A callable that is used to cast the value in the
                     :class:`Headers`.  If a :exc:`ValueError` is raised
                     by this callable the default value is returned.

        .. versionchanged:: 2.3
            The ``as_bytes`` parameter is deprecated and will be removed
            in Werkzeug 2.4.

        .. versionchanged:: 0.9
            The ``as_bytes`` parameter was added.
        """
        if as_bytes is not None:
            warnings.warn(
                "The 'as_bytes' parameter is deprecated and will be"
                " removed in Werkzeug 2.4.",
                DeprecationWarning,
                stacklevel=2,
            )

        try:
            rv = self.__getitem__(key, _get_mode=True)
        except KeyError:
            return default
        if as_bytes:
            rv = rv.encode("latin1")
        if type is None:
            return rv
        try:
            return type(rv)
        except ValueError:
            return default

    def getlist(self, key, type=None, as_bytes=None):
        """Return the list of items for a given key. If that key is not in the
        :class:`Headers`, the return value will be an empty list.  Just like
        :meth:`get`, :meth:`getlist` accepts a `type` parameter.  All items will
        be converted with the callable defined there.

        :param key: The key to be looked up.
        :param type: A callable that is used to cast the value in the
                     :class:`Headers`.  If a :exc:`ValueError` is raised
                     by this callable the value will be removed from the list.
        :return: a :class:`list` of all the values for the key.

        .. versionchanged:: 2.3
            The ``as_bytes`` parameter is deprecated and will be removed
            in Werkzeug 2.4.

        .. versionchanged:: 0.9
            The ``as_bytes`` parameter was added.
        """
        if as_bytes is not None:
            warnings.warn(
                "The 'as_bytes' parameter is deprecated and will be"
                " removed in Werkzeug 2.4.",
                DeprecationWarning,
                stacklevel=2,
            )

        ikey = key.lower()
        result = []
        for k, v in self:
            if k.lower() == ikey:
                if as_bytes:
                    v = v.encode("latin1")
                if type is not None:
                    try:
                        v = type(v)
                    except ValueError:
                        continue
                result.append(v)
        return result

    def get_all(self, name):
        """Return a list of all the values for the named field.

        This method is compatible with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.get_all` method.
        """
        return self.getlist(name)

    def items(self, lower=False):
        for key, value in self:
            if lower:
                key = key.lower()
            yield key, value

    def keys(self, lower=False):
        for key, _ in self.items(lower):
            yield key

    def values(self):
        for _, value in self.items():
            yield value

    def extend(self, *args, **kwargs):
        """Extend headers in this object with items from another object
        containing header items as well as keyword arguments.

        To replace existing keys instead of extending, use
        :meth:`update` instead.

        If provided, the first argument can be another :class:`Headers`
        object, a :class:`MultiDict`, :class:`dict`, or iterable of
        pairs.

        .. versionchanged:: 1.0
            Support :class:`MultiDict`. Allow passing ``kwargs``.
        """
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")

        if args:
            for key, value in iter_multi_items(args[0]):
                self.add(key, value)

        for key, value in iter_multi_items(kwargs):
            self.add(key, value)

    def __delitem__(self, key, _index_operation=True):
        if _index_operation and isinstance(key, (int, slice)):
            del self._list[key]
            return
        key = key.lower()
        new = []
        for k, v in self._list:
            if k.lower() != key:
                new.append((k, v))
        self._list[:] = new

    def remove(self, key):
        """Remove a key.

        :param key: The key to be removed.
        """
        return self.__delitem__(key, _index_operation=False)

    def pop(self, key=None, default=_missing):
        """Removes and returns a key or index.

        :param key: The key to be popped.  If this is an integer the item at
                    that position is removed, if it's a string the value for
                    that key is.  If the key is omitted or `None` the last
                    item is removed.
        :return: an item.
        """
        if key is None:
            return self._list.pop()
        if isinstance(key, int):
            return self._list.pop(key)
        try:
            rv = self[key]
            self.remove(key)
        except KeyError:
            if default is not _missing:
                return default
            raise
        return rv

    def popitem(self):
        """Removes a key or index and returns a (key, value) item."""
        return self.pop()

    def __contains__(self, key):
        """Check if a key is present."""
        try:
            self.__getitem__(key, _get_mode=True)
        except KeyError:
            return False
        return True

    def __iter__(self):
        """Yield ``(key, value)`` tuples."""
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    def add(self, _key, _value, **kw):
        """Add a new header tuple to the list.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes::

        >>> d = Headers()
        >>> d.add('Content-Type', 'text/plain')
        >>> d.add('Content-Disposition', 'attachment', filename='foo.png')

        The keyword argument dumping uses :func:`dump_options_header`
        behind the scenes.

        .. versionadded:: 0.4.1
            keyword arguments were added for :mod:`wsgiref` compatibility.
        """
        if kw:
            _value = _options_header_vkw(_value, kw)
        _key = _str_header_key(_key)
        _value = _str_header_value(_value)
        self._list.append((_key, _value))

    def add_header(self, _key, _value, **_kw):
        """Add a new header tuple to the list.

        An alias for :meth:`add` for compatibility with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.add_header` method.
        """
        self.add(_key, _value, **_kw)

    def clear(self):
        """Clears all headers."""
        del self._list[:]

    def set(self, _key, _value, **kw):
        """Remove all header tuples for `key` and add a new one.  The newly
        added key either appears at the end of the list if there was no
        entry or replaces the first one.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes.  See :meth:`add` for
        more information.

        .. versionchanged:: 0.6.1
           :meth:`set` now accepts the same arguments as :meth:`add`.

        :param key: The key to be inserted.
        :param value: The value to be inserted.
        """
        if kw:
            _value = _options_header_vkw(_value, kw)
        _key = _str_header_key(_key)
        _value = _str_header_value(_value)
        if not self._list:
            self._list.append((_key, _value))
            return
        listiter = iter(self._list)
        ikey = _key.lower()
        for idx, (old_key, _old_value) in enumerate(listiter):
            if old_key.lower() == ikey:
                # replace first occurrence
                self._list[idx] = (_key, _value)
                break
        else:
            self._list.append((_key, _value))
            return
        self._list[idx + 1 :] = [t for t in listiter if t[0].lower() != ikey]

    def setlist(self, key, values):
        """Remove any existing values for a header and add new ones.

        :param key: The header key to set.
        :param values: An iterable of values to set for the key.

        .. versionadded:: 1.0
        """
        if values:
            values_iter = iter(values)
            self.set(key, next(values_iter))

            for value in values_iter:
                self.add(key, value)
        else:
            self.remove(key)

    def setdefault(self, key, default):
        """Return the first value for the key if it is in the headers,
        otherwise set the header to the value given by ``default`` and
        return that.

        :param key: The header key to get.
        :param default: The value to set for the key if it is not in the
            headers.
        """
        if key in self:
            return self[key]

        self.set(key, default)
        return default

    def setlistdefault(self, key, default):
        """Return the list of values for the key if it is in the
        headers, otherwise set the header to the list of values given
        by ``default`` and return that.

        Unlike :meth:`MultiDict.setlistdefault`, modifying the returned
        list will not affect the headers.

        :param key: The header key to get.
        :param default: An iterable of values to set for the key if it
            is not in the headers.

        .. versionadded:: 1.0
        """
        if key not in self:
            self.setlist(key, default)

        return self.getlist(key)

    def __setitem__(self, key, value):
        """Like :meth:`set` but also supports index/slice based setting."""
        if isinstance(key, (slice, int)):
            if isinstance(key, int):
                value = [value]
            value = [(_str_header_key(k), _str_header_value(v)) for (k, v) in value]
            if isinstance(key, int):
                self._list[key] = value[0]
            else:
                self._list[key] = value
        else:
            self.set(key, value)

    def update(self, *args, **kwargs):
        """Replace headers in this object with items from another
        headers object and keyword arguments.

        To extend existing keys instead of replacing, use :meth:`extend`
        instead.

        If provided, the first argument can be another :class:`Headers`
        object, a :class:`MultiDict`, :class:`dict`, or iterable of
        pairs.

        .. versionadded:: 1.0
        """
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 arguments, got {len(args)}")

        if args:
            mapping = args[0]

            if isinstance(mapping, (Headers, MultiDict)):
                for key in mapping.keys():
                    self.setlist(key, mapping.getlist(key))
            elif isinstance(mapping, dict):
                for key, value in mapping.items():
                    if isinstance(value, (list, tuple)):
                        self.setlist(key, value)
                    else:
                        self.set(key, value)
            else:
                for key, value in mapping:
                    self.set(key, value)

        for key, value in kwargs.items():
            if isinstance(value, (list, tuple)):
                self.setlist(key, value)
            else:
                self.set(key, value)

    def to_wsgi_list(self):
        """Convert the headers into a list suitable for WSGI.

        :return: list
        """
        return list(self)

    def copy(self):
        return self.__class__(self._list)

    def __copy__(self):
        return self.copy()

    def __str__(self):
        """Returns formatted headers suitable for HTTP transmission."""
        strs = []
        for key, value in self.to_wsgi_list():
            strs.append(f"{key}: {value}")
        strs.append("\r\n")
        return "\r\n".join(strs)

    def __repr__(self):
        return f"{type(self).__name__}({list(self)!r})"


def _options_header_vkw(value: str, kw: dict[str, t.Any]):
    return http.dump_options_header(
        value, {k.replace("_", "-"): v for k, v in kw.items()}
    )


def _str_header_key(key: t.Any) -> str:
    if not isinstance(key, str):
        warnings.warn(
            "Header keys must be strings. Passing other types is deprecated and will"
            " not be supported in Werkzeug 2.4.",
            DeprecationWarning,
            stacklevel=2,
        )

        if isinstance(key, bytes):
            key = key.decode("latin-1")
        else:
            key = str(key)

    return key


_newline_re = re.compile(r"[\r\n]")


def _str_header_value(value: t.Any) -> str:
    if isinstance(value, bytes):
        warnings.warn(
            "Passing bytes as a header value is deprecated and will not be supported in"
            " Werkzeug 2.4.",
            DeprecationWarning,
            stacklevel=2,
        )
        value = value.decode("latin-1")

    if not isinstance(value, str):
        value = str(value)

    if _newline_re.search(value) is not None:
        raise ValueError("Header values must not contain newline characters.")

    return value


class EnvironHeaders(ImmutableHeadersMixin, Headers):
    """Read only version of the headers from a WSGI environment.  This
    provides the same interface as `Headers` and is constructed from
    a WSGI environment.
    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for
    HTTP exceptions.
    """

    def __init__(self, environ):
        self.environ = environ

    def __eq__(self, other):
        return self.environ is other.environ

    __hash__ = None

    def __getitem__(self, key, _get_mode=False):
        # _get_mode is a no-op for this class as there is no index but
        # used because get() calls it.
        if not isinstance(key, str):
            raise KeyError(key)
        key = key.upper().replace("-", "_")
        if key in {"CONTENT_TYPE", "CONTENT_LENGTH"}:
            return self.environ[key]
        return self.environ[f"HTTP_{key}"]

    def __len__(self):
        # the iter is necessary because otherwise list calls our
        # len which would call list again and so forth.
        return len(list(iter(self)))

    def __iter__(self):
        for key, value in self.environ.items():
            if key.startswith("HTTP_") and key not in {
                "HTTP_CONTENT_TYPE",
                "HTTP_CONTENT_LENGTH",
            }:
                yield key[5:].replace("_", "-").title(), value
            elif key in {"CONTENT_TYPE", "CONTENT_LENGTH"} and value:
                yield key.replace("_", "-").title(), value

    def copy(self):
        raise TypeError(f"cannot create {type(self).__name__!r} copies")


# circular dependencies
from .. import http
