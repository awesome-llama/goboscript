# Functions

Functions are procedures (custom blocks) that can return values (or structs).
Functions are always **Run without screen refresh** and must be only called within
**Run without screen refresh** procedures or functions to prevent undefined behavior.
Functions must always terminate with a return statement. Using `stop_this_script`
inside functions is undefined behavior.

## Declaring a function

```goboscript
func my_function(x, y) {
    return $x + $y;
}
```

```goboscript
func my_function(x, y) type_name {
    return type_name { ... };
}
```

## Calling a function

```goboscript
say my_function(1, 2);
```
