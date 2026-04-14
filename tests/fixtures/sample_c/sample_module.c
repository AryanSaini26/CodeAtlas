#include <stdio.h>
#include <stdlib.h>
#include "utils.h"

typedef struct {
    int x;
    int y;
} Point;

typedef enum {
    RED,
    GREEN,
    BLUE,
} Color;

typedef int (*BinaryOp)(int, int);

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

int compute(int a, int b) {
    int sum = add(a, b);
    int product = multiply(a, b);
    return sum + product;
}

void print_point(Point p) {
    printf("(%d, %d)\n", p.x, p.y);
}
