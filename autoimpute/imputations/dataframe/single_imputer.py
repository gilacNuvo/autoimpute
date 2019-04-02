"""This module performs single imputations for cross-sectional Series.

This module contains one class - the SingleImputer. Use this class to perform
one imputation for each Series within a DataFrame. The methods available are
all univariate - they do not use any other features to perform a given Series'
imputation. Rather, they rely on the Series itself.
"""

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted
from autoimpute.utils import check_nan_columns
from autoimpute.imputations import method_names
from .base_imputer import BaseImputer
from ..series import DefaultSingleImputer
from ..series import MeanImputer, MedianImputer, ModeImputer
from ..series import NormImputer, CategoricalImputer
from ..series import RandomImputer, InterpolateImputer
methods = method_names

# pylint:disable=attribute-defined-outside-init
# pylint:disable=arguments-differ
# pylint:disable=protected-access
# pylint:disable=too-many-arguments
# pylint:disable=too-many-instance-attributes

class SingleImputer(BaseImputer, BaseEstimator, TransformerMixin):
    """Techniques to impute Series with missing values one time.

    The SingleImputer class takes a DataFrame and performs single imputations
    on each Series within the DataFrame. The SingleImputer does one pass for
    each column, and it supports univariate methods only.

    The class is a valid transformer that can be used in an sklearn pipeline
    because it inherits from the TransformerMixin and implements both fit and
    transform methods.

    Some of the imputers are inductive (i.e. fit and transform for new data).
    Others are transductive (i.e. fit_transform only). Transductive methods
    return None during the "fitting" stage. This behavior is a bit odd, but
    it allows inductive and transductive methods within the same Imputer.

    Attributes:
        strategies (dict): dictionary of supported imputation methods.
            Key = imputation name; Value = function to perform imputation.
            `default` imputes mean for numerical, mode for categorical.
            `mean` imputes missing values with the average of the series.
            `median` imputes missing values with the median of the series.
            `mode` imputes missing values with the mode of the series.
                Method handles more than one mode (see ModeImputer for info).
            `random` imputes w/ random choice from set of Series unique vals.
            `norm` imputes series using random draws from normal distribution.
                Mean and std calculated from observed values of the Series.
            `categorical` imputes series using random draws from pmf.
                Proportions calculated from non-missing category instances.
            `interpolate` imputes series using chosen interpolation method.
                Default is linear. See InterpolateImputer for more info.
    """

    strategies = {
        methods.DEFAULT: DefaultSingleImputer,
        methods.MEAN: MeanImputer,
        methods.MEDIAN: MedianImputer,
        methods.MODE:  ModeImputer,
        methods.RANDOM: RandomImputer,
        methods.NORM: NormImputer,
        methods.CATEGORICAL: CategoricalImputer,
        methods.INTERPOLATE: InterpolateImputer
    }

    def __init__(self, strategy="default", imp_kwgs=None,
                 copy=True, verbose=False):
        """Create an instance of the SingleImputer class.

        As with sklearn classes, all arguments take default values. Therefore,
        SingleImputer() creates a valid class instance. The instance is used to
        set up an imputer and perform checks on arguments.

        Args:
            strategy (str, iter, dict; optional): strategies for imputation.
                Default value is str -> "default". I.e. default imputation.
                If str, single strategy broadcast to all series in DataFrame.
                If iter, must provide 1 strategy per column. Each method within
                iterator applies to column with same index value in DataFrame.
                If dict, must provide key = column name, value = imputer.
                Dict the most flexible and PREFERRED way to create custom
                imputation strategies if not using the default. Dict does not
                require method for every column; just those specified as keys.
            imp_kwgs (dict, optional): keyword arguments for each imputer.
                Default is None, which means default imputer created to match
                specific strategy. imp_kwgs keys can be either columns or
                strategies. If strategies, each column given that strategy is
                instantiated with same arguments.
            verbose (bool, optional): print more information to console.
                Default value is False.
            copy (bool, optional): create copy of DataFrame or operate inplace.
                Default value is True. Copy created.
        """
        BaseImputer.__init__(
            self,
            imp_kwgs=imp_kwgs,
            scaler=None,
            verbose=verbose
        )
        self.strategy = strategy
        self.copy = copy

    @property
    def strategy(self):
        """Property getter to return the value of the strategy property"""
        return self._strategy

    @strategy.setter
    def strategy(self, s):
        """Validate the strategy property to ensure it's type and value.

        Class instance only possible if strategy is proper type, as outlined
        in the init method. Passes supported strategies and user-defined
        strategy to helper method, which performs strategy checks.

        Args:
            s (str, iter, dict): Strategy passed as arg to class instance.

        Raises:
            ValueError: Strategies not valid (not in allowed strategies).
            TypeError: Strategy must be a string, tuple, list, or dict.
            Both errors raised through helper method `check_strategy_allowed`.
        """
        strat_names = self.strategies.keys()
        self._strategy = self.check_strategy_allowed(strat_names, s)

    def _fit_strategy_validator(self, X):
        """Internal helper method to validate strategies appropriate for fit.

        Checks whether strategies match with type of column they are applied
        to. If not, error is raised through `check_strategy_fit` method.
        """
        # remove nan columns and store colnames
        s = self.strategy
        cols = X.columns.tolist()
        self._strats = self.check_strategy_fit(s, cols)

    def _transform_strategy_validator(self, X):
        """Private method to validate before transformation phase."""
        # initial checks before transformation
        check_is_fitted(self, "statistics_")

        # check columns
        X_cols = X.columns.tolist()
        fit_cols = set(self._strats.keys())
        diff_fit = set(fit_cols).difference(X_cols)
        if diff_fit:
            err = "Same columns that were fit must appear in transform."
            raise ValueError(err)

    @check_nan_columns
    def fit(self, X):
        """Fit imputation methods to each column within a DataFrame.

        The fit method calclulates the `statistics` necessary to later
        transform a dataset (i.e. perform actual imputatations). Inductive
        methods (mean, mode, median, etc.) calculate statistic on the fit
        data, then impute new missing data with that value. Transductive
        methods (linear) don't calculate anything during fit, as they
        apply imputation during transformation phase only.

        Args:
            X (pd.DataFrame): pandas DataFrame on which imputer is fit.

        Returns:
            self: instance of the SingleImputer class.
        """
        # create statistics if validated
        self._fit_strategy_validator(X)
        self.statistics_ = {}

        # header print statement if verbose = true
        if self.verbose:
            ft = "FITTING IMPUTATION METHODS TO DATA..."
            st = "Strategies used to fit each column:"
            print(f"{ft}\n{st}\n{'-'*len(st)}")

        # perform fit on each column, depending on that column's strategy
        # note that right now, operations are COLUMN-by-COLUMN, iteratively
        # in the future, we should handle univar methods in parallel
        for column, method in self._strats.items():
            imp = self.strategies[method]
            imp_params = self._fit_init_params(column, method, self.imp_kwgs)

            # try to create an instance of the imputer, given the args
            try:
                if imp_params is None:
                    imputer = imp()
                else:
                    imputer = imp(**imp_params)
            except TypeError as te:
                name = imp.__name__
                err = f"Invalid arguments passed to {name} __init__ method."
                raise ValueError(err) from te

            # print strategies if verbose
            if self.verbose:
                print(f"Column: {column}, Strategy: {method}")

            # if succeeds, fit the method to the column of interest
            # note - have to fit X regardless of whether any data missing
            # transform step may have missing data
            # so fit each column that appears in the given strategies
            imputer.fit(X[column])
            self.statistics_[column] = imputer

        return self

    @check_nan_columns
    def transform(self, X):
        """Impute each column within a DataFrame using fit imputation methods.

        The transform step performs the actual imputations. Given a dataset
        previously fit, `transform` imputes each column with it's respective
        imputed values from fit (in the case of inductive) or performs new fit
        and transform in one sweep (in the case of transductive).

        Args:
            X (pd.DataFrame): fit DataFrame to impute.

        Returns:
            X (pd.DataFrame): imputed in place or copy of original.

        Raises:
            ValueError: same columns must appear in fit and transform.
        """
        if self.copy:
            X = X.copy()
        self._transform_strategy_validator(X)
        if self.verbose:
            trans = "PERFORMING IMPUTATIONS ON DATA BASED ON FIT..."
            print(f"{trans}\n{'-'*len(trans)}")

        # transformation logic
        # same applies, should be able to handel in parallel
        self.imputed_ = {}
        for column, imputer in self.statistics_.items():
            imp_ix = X[column][X[column].isnull()].index
            self.imputed_[column] = imp_ix.tolist()

            # print to console for transformation if self.verbose
            if self.verbose:
                strat = imputer.statistics_["strategy"]
                print(f"Transforming {column} with strategy '{strat}'")
                if not imp_ix.empty:
                    print(f"Numer of imputations to perform: {imp_ix.size}")
                else:
                    print(f"No imputations, moving to next column...")

            # move onto next column if no imputations to make
            if imp_ix.empty:
                continue
            X.loc[imp_ix, column] = imputer.impute(X[column])
        return X
