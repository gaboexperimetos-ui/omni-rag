---
title: "Álgebra lineal"
tags: [matematicas, algebra, matrices, sistemas]
---

# Álgebra lineal

## Matrices

Una matriz $A \in \mathbb{R}^{m \times n}$ es un array rectangular.

### Operaciones

- Suma: $(A+B)_{ij} = A_{ij}+B_{ij}$ (mismo tamaño)
- Producto escalar: $(cA)_{ij} = c A_{ij}$
- Producto matricial: $(AB)_{ij} = \sum_k A_{ik}B_{kj}$

El producto no es conmutativo: $AB \neq BA$ en general.

## Determinante

Para $2\times2$:

$$\det\begin{pmatrix}a&b\\c&d\end{pmatrix} = ad-bc$$

Para $n\times n$, desarrollo por cofactores o eliminación gaussiana.

Propiedades: $\det(AB)=\det A\det B$, $\det A^T=\det A$, $\det A \neq 0 \iff A$ invertible.

## Sistemas lineales

$A\vec x = \vec b$.

- Gauss-Jordan: forma escalonada reducida
- Regla de Cramer: $x_i = \frac{\det A_i}{\det A}$ (si $\det A \neq 0$)
- Inversa: $\vec x = A^{-1}\vec b$

## Valores y vectores propios

$A\vec v = \lambda \vec v$. El polinomio característico es $\det(A-\lambda I)=0$.

Aplicaciones: sistemas dinámicos, PCA, vibraciones (ver [[Índice — Física]]).