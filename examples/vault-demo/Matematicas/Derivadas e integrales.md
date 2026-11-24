---
title: "Derivadas e integrales"
tags: [matematicas, calculo, derivadas, integrales]
---

# Derivadas e integrales

## Derivadas

La derivada de $f$ en $x_0$ es el límite:

$$f'(x_0) = \lim_{h \to 0} \frac{f(x_0+h)-f(x_0)}{h}$$

Si existe, $f$ es derivable en $x_0$.

### Reglas básicas

| Función | Derivada |
|---------|----------|
| $c$ | $0$ |
| $x^n$ | $n x^{n-1}$ |
| $e^x$ | $e^x$ |
| $\ln x$ | $1/x$ |
| $\sin x$ | $\cos x$ |
| $\cos x$ | $-\sin x$ |

### Regla de la cadena

$$(g \circ f)'(x) = g'(f(x)) \cdot f'(x)$$

Ejemplo: $\frac{d}{dx} \sin(x^2) = \cos(x^2) \cdot 2x$.

## Integrales

La integral indefinida es la antiderivada:

$$\int f(x)\,dx = F(x) + C \quad \text{si} \quad F' = f$$

La integral definida calcula el área bajo la curva:

$$\int_a^b f(x)\,dx = F(b) - F(a)$$

### Técnicas

- Sustitución: $u = g(x)$, $du = g'(x)\,dx$
- Integración por partes: $\int u\,dv = uv - \int v\,du$
- Fracciones parciales para funciones racionales

Ver [[Álgebra lineal]] para sistemas que salen al integrar por partes.