"""Native Linear Regression implementatie zonder externe dependencies."""
import logging
from typing import List, Tuple

_LOGGER = logging.getLogger(__name__)


class LinearRegression:
    """
    Eenvoudige Multiple Linear Regression implementatie.
    
    Gebruikt Ordinary Least Squares (OLS) methode met matrix operaties.
    Ondersteunt multiple features (X kan meerdere kolommen hebben).
    """

    def __init__(self):
        """Initialize."""
        self.coefficients: List[float] = []
        self.intercept: float = 0.0
        self.n_features: int = 0
        self._is_fitted: bool = False

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        """
        Fit het model op training data.
        
        Args:
            X: Feature matrix (list of lists), shape (n_samples, n_features)
            y: Target vector (list), shape (n_samples,)
        """
        if len(X) != len(y):
            raise ValueError(f"X en y moeten dezelfde lengte hebben: {len(X)} != {len(y)}")
        
        if len(X) == 0:
            raise ValueError("Training data mag niet leeg zijn")
        
        n_samples = len(X)
        self.n_features = len(X[0])
        
        # Voeg intercept kolom toe (alle 1's) aan X
        X_with_intercept = [[1.0] + row for row in X]
        n_features_with_intercept = self.n_features + 1
        
        # Bereken (X^T * X)
        XtX = self._matrix_multiply_transpose(X_with_intercept, X_with_intercept)
        
        # Bereken (X^T * y)
        Xty = self._matrix_vector_multiply_transpose(X_with_intercept, y)
        
        # Los op: (X^T * X)^-1 * (X^T * y) = coefficients
        try:
            XtX_inv = self._matrix_inverse(XtX)
            coefficients_with_intercept = self._matrix_vector_multiply(XtX_inv, Xty)
            
            # Eerste coefficient is intercept, rest zijn feature coefficients
            self.intercept = coefficients_with_intercept[0]
            self.coefficients = coefficients_with_intercept[1:]
            
            self._is_fitted = True
            
            _LOGGER.debug(
                f"Model fitted: intercept={self.intercept:.4f}, "
                f"coefficients={[f'{c:.4f}' for c in self.coefficients]}"
            )
            
        except Exception as err:
            _LOGGER.error(f"Fout bij matrix inversie: {err}")
            raise ValueError(f"Kan model niet fitten: {err}")

    def predict(self, X: List[List[float]]) -> List[float]:
        """
        Voorspel target waarden voor nieuwe data.
        
        Args:
            X: Feature matrix, shape (n_samples, n_features)
            
        Returns:
            Predicted values, shape (n_samples,)
        """
        if not self._is_fitted:
            raise ValueError("Model moet eerst gefit worden met fit()")
        
        predictions = []
        for row in X:
            if len(row) != self.n_features:
                raise ValueError(
                    f"Feature count mismatch: verwacht {self.n_features}, kreeg {len(row)}"
                )
            
            # y = intercept + sum(coef_i * x_i)
            prediction = self.intercept
            for i, value in enumerate(row):
                prediction += self.coefficients[i] * value
            
            predictions.append(prediction)
        
        return predictions

    def score(self, X: List[List[float]], y: List[float]) -> float:
        """
        Bereken R² score (coefficient of determination).
        
        R² = 1 - (SS_res / SS_tot)
        waar SS_res = sum of squared residuals
             SS_tot = total sum of squares
        
        Returns:
            R² score tussen 0 en 1 (hoger is beter)
        """
        if not self._is_fitted:
            raise ValueError("Model moet eerst gefit worden")
        
        predictions = self.predict(X)
        
        # Bereken mean van y
        y_mean = sum(y) / len(y)
        
        # SS_tot = sum((y_i - y_mean)^2)
        ss_tot = sum((y_i - y_mean) ** 2 for y_i in y)
        
        # SS_res = sum((y_i - y_pred_i)^2)
        ss_res = sum((y[i] - predictions[i]) ** 2 for i in range(len(y)))
        
        # R² = 1 - (SS_res / SS_tot)
        if ss_tot == 0:
            return 0.0
        
        r_squared = 1.0 - (ss_res / ss_tot)
        return r_squared

    # ===== Matrix operaties =====

    def _matrix_multiply_transpose(self, A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
        """Bereken A^T * B."""
        n = len(A[0])  # columns in A = rows in A^T
        m = len(B[0])  # columns in B
        
        result = [[0.0] * m for _ in range(n)]
        
        for i in range(n):
            for j in range(m):
                for k in range(len(A)):
                    result[i][j] += A[k][i] * B[k][j]
        
        return result

    def _matrix_vector_multiply_transpose(self, A: List[List[float]], v: List[float]) -> List[float]:
        """Bereken A^T * v."""
        n = len(A[0])  # columns in A
        result = [0.0] * n
        
        for i in range(n):
            for j in range(len(A)):
                result[i] += A[j][i] * v[j]
        
        return result

    def _matrix_vector_multiply(self, A: List[List[float]], v: List[float]) -> List[float]:
        """Bereken A * v."""
        result = [0.0] * len(A)
        
        for i in range(len(A)):
            for j in range(len(v)):
                result[i] += A[i][j] * v[j]
        
        return result

    def _matrix_inverse(self, matrix: List[List[float]]) -> List[List[float]]:
        """
        Bereken matrix inverse met Gauss-Jordan eliminatie.
        
        Augmented matrix methode: [A | I] -> [I | A^-1]
        """
        n = len(matrix)
        
        # Maak een kopie en voeg identity matrix toe
        augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] 
                     for i, row in enumerate(matrix)]
        
        # Forward elimination
        for i in range(n):
            # Zoek pivot (grootste waarde in kolom)
            max_row = i
            for k in range(i + 1, n):
                if abs(augmented[k][i]) > abs(augmented[max_row][i]):
                    max_row = k
            
            # Swap rijen
            augmented[i], augmented[max_row] = augmented[max_row], augmented[i]
            
            # Check voor singuliere matrix
            if abs(augmented[i][i]) < 1e-10:
                raise ValueError("Matrix is singulier (niet inverteerbaar)")
            
            # Maak pivot 1
            pivot = augmented[i][i]
            for j in range(2 * n):
                augmented[i][j] /= pivot
            
            # Elimineer kolom
            for k in range(n):
                if k != i:
                    factor = augmented[k][i]
                    for j in range(2 * n):
                        augmented[k][j] -= factor * augmented[i][j]
        
        # Extract inverse (rechter helft van augmented matrix)
        inverse = [row[n:] for row in augmented]
        
        return inverse
