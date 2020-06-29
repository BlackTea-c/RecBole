# -*- encoding: utf-8 -*-
'''
@File    :   evaluator.py
@Time    :   2020/06/27 13:34:36
@Author  :   tsotfsk
@Version :   1.0
@Contact :   tsotfsk@outlook.com
'''

# here put the import lib

import pandas as pd
import utils


# 'Precision', 'Hit', 'Recall', 'MAP', 'NDCG', 'MRR'
metric_name = {metric.lower() : metric for metric in ['Hit', 'Recall', 'MRR']}

class BaseEvaluator(object):
    """base class for all evaluator
    """
    def __init__(self):
        pass

    def metrics_info(self, merged_data):
        """Get all metrics information for the merged data.

        Returns:
            str: A string consist of all metrics information.
        """
        raise NotImplementedError

    def evaluate(self, result, test_data):
        """Evaluate the result generated by the train model and get metrics information on the specified data

        Args:
            result ([type]) : TODO
            test_data ([type]) : TODO

        Returns:
            A string which consists of all information about the result on the test_data 
        """        
        return NotImplementedError

# TODO 这里应该是加速的重点
class UnionEvaluator(BaseEvaluator):
    """`UnionEvaluator` evaluates results on ungrouped data.
     
    """
    def __init__(self, eval_metric, topk, workers):
        """[summary]

        Args:
            eval_metric ([type]): [description]
            topk ([type]): [description]
            workers ([type]): [description]
        """        
        super(UnionEvaluator, self).__init__()
        self.topk = topk
        self.eval_metric = eval_metric
        self.workers = workers

    def get_ground_truth(self, users, test_data):
        """It is a interface which can get the ground truth of the users from the test data.

        Args:
            users (list): [description]
            test_data ([type]): TODO [description]

        Returns:
            users (list): a list of users.
            items (list): users' ground truth.
        """        
        # TODO 对接
        users, items = test_data
        return users, items
    
    def get_result_pairs(self, result):
        """[summary]

        Args:
            result ([type]): [description]

        Returns:
            [type]: [description]
        """        
        # TODO 对接
        users, items, scores = result
        return users, items, scores

    def merge_data(self, result, test_data):
        """Merging result and test_data which can help our evaluation

        Args:
            result (tuple): a tuple of (users, items), both `users` and `items` are lists and they have the same length.
            test_data ([type]): TODO [description]

        Returns:
            (pandas.core.frame.DataFrame): such as 
        """        
        users, items, scores = self.get_result_pairs(result)
        result_df = pd.DataFrame({'user_id':users, 'item_id':items, 'score':scores})
        # XXX 这里全排序应该不好，只取topk会快一点，而且topk可以从大到小测，这个应该是可以加速很多的地方
        result_df['rank'] = result_df.groupby('user_id')['score'].rank(method='first', ascending=False)

        users, items =  self.get_ground_truth(users, test_data)
        truth_df = pd.DataFrame({'user_id':users, 'item_id':items})

        # truth_df['count'] = truth_df.groupby('user_id')['item_id'].transform('count')
        merged_data = truth_df.merge(result_df, on=['user_id', 'item_id'], how='left')
        merged_data['rank'].fillna(-1, inplace=True)
        return merged_data

    # @profile
    def metric_info(self, merged_data):
        """Get all metrics information for the merged data.

        Returns:
            str: A string consist of all metrics information
        """

        metric_info = []
        for k in self.topk:
            for method in self.eval_metric:
                eval_fuc = getattr(utils, method)
                score = eval_fuc(merged_data, k)
                metric_info.append('{:>5}@{} : {:5f}'.format(metric_name[method], k, score))
        return '\t'.join(metric_info)

    def evaluate(self, result, test_data):
        """Evaluate `model`.

        Args:
            result: TODO
            test_data: TODO

        Returns:
            str: A string consist of all results, such as
                Hit@5 : 0.484848      Recall@5 : 0.162734        Hit@7 : 0.727273      Recall@7 : 0.236760`.
        """ 
        merged_data = self.merge_data(result, test_data)
        info_str = self.metric_info(merged_data)
        return info_str

class GroupEvaluator(UnionEvaluator):
    """`GroupedEvaluator` evaluates results in user groups.

    This class evaluates the ranking performance of models in user groups,
    which are split according to the numbers of users' interactions in
    `training data`. This class can be activated by the argument
    `group_view`, which must be a list of integers.
    For example, if `group_view = [10, 30, 50, 100]`, users will be split into
    four groups: `(0, 10]`, `(10, 30]`, `(30, 50]`, `(50, 100], (100, -]`. 
    """
    def __init__(self, group_view, eval_metric, topk, workers):
        """[summary]

        Args:
            group_view (list): 'group_view' controls the user group on the test data.
            eval_metric (list): 'eval_metric' controls the metrics on the test data.
            topk (list): `top_k` controls the Top-K item ranking
                performance. 
            workers (int): `workers` controls the number of threads.
        """        
        super(GroupEvaluator, self).__init__(eval_metric, topk, workers)
        self.group_view = group_view
        self.group_names = self.get_group_names()
        # print(self.group_names)

    def groupby(self, df, col):     
        return df.groupby(col, sort=True)

    def get_group_names(self):
        """split self.group_view into several intervals

        Returns:
            a list of strings which contains the sliced groups' name
        """        
        group_view = [0] + self.group_view + ['-']
        group_names = []
        for begin, end in zip(group_view[:-1], group_view[1:]):
            group_names.append('({},{}]'.format(begin, end))
        return group_names

    def get_grouped_data(self, merged_data, test_data):
        """ a interface which can split the users into groups.

        Args:
            merged_data (pandas.core.frame.DataFrame): This data contains information such as rankings and scores of ground truth.
            test_data ([type]):TODO [description]

        Returns:
            (pandas.core.frame.DataFrame): This is a new merged_data which is added to a new column named `group_id`.
        """        
        # TODO 要加group_id, 这个要和test_data 对接一下, 我可以转成df，然后apply一下
        merged_data['group_id'] = merged_data['user_id'] % 3
        
        return merged_data

    def evaluate_groups(self, groups):
        """evaluate_groups and get a merged string

        Args:
            groups (pandas.core.groupby.generic.DataFrameGroupBy): data grouped by `group_id`.

        Returns:
            str: A string consist of all results.
        """       

        info_list = []
        for index, group in groups:
            info_str = self.metric_info(group)
            info_list.append('{:<5}\t{}'.format(self.group_names[index], info_str))
        return '\n'.join(info_list)

    def evaluate(self, result, test_data):
        """Evaluate `model`.

        Args:
            result: TODO
            test_data: TODO

        Returns:
            str: A string consist of all results, such as
                (0,1]     Hit@5 : 0.647059      Recall@5 : 0.201914        Hit@8 : 0.823529      Recall@8 : 0.296802
                (1,5]     Hit@5 : 0.515152      Recall@5 : 0.160762        Hit@8 : 0.848485      Recall@8 : 0.275144
                (5,-]     Hit@5 : 0.636364      Recall@5 : 0.153968        Hit@8 : 0.848485      Recall@8 : 0.223557
        """ 
        merged_data = self.merge_data(result, test_data)
        grouped_data = self.get_grouped_data(merged_data, test_data)
        groups = self.groupby(grouped_data, 'group_id')
        info_str = self.evaluate_groups(groups)
        return info_str
        
class Evaluator(BaseEvaluator):
    """`Evaluator` is the interface to evaluate models.

    `Evaluator` contains various evaluation protocols:

      1) Evaluation metrics of this class are configurable via the
      argument `eval_metric`. Now it can support three metrics which
      contains `Recall`, `NDCG` and `MRR`.

      2) It can automatically fit both leave-one-out and fold-out data
      without any additional statement.
      

      3) The ranking performance of models can be viewed in user
      groups, which are split according to the numbers of users' interactions
      in `training data`. It is configurable via the argument `group_view`.

    """
    def __init__(self, config):
        """Initialize the evaluator by the global configuration file.

        Args:
            config ([type]): TODO the config can be used as a dictionary, such as

            self.group_view = config['group_view']
            self.eval_metric = config['metric']
            self.topk = config['topk']
            self.workers = config['workers']
        """        
        super(Evaluator, self).__init__()

        self.group_view = config['group_view']
        self.eval_metric = config['metric']
        self.topk = config['topk']
        self.workers = config['workers']  # TODO 多进程，但是windows可能有点难搞, 貌似要在__main__里
 
        # XXX 这种类型检查应该放到哪呢?放在config部分一次判断，还是分散在各模块中呢？
        self._check_args()

        if self.group_view is not None:
            self.evaluator = GroupEvaluator(self.group_view, self.eval_metric, self.topk, self.workers)
        else:
            self.evaluator = UnionEvaluator(self.eval_metric, self.topk, self.workers)

    def _check_args(self):

        # check group_view
        if isinstance(self.group_view, (int, list, None.__class__)):
            if isinstance(self.group_view, int):
                assert self.group_view > 0, 'group_view must be a pistive integer or a list of postive integers'
                self.group_view = [self.group_view]
        else:
            raise TypeError('The group_view muse be int or list')
        if self.group_view is not None:
            for number in self.group_view:
                assert isinstance(number, int) and number > 0, '{} in group_view is not a postive integer'.format(number)
            self.group_view = sorted(self.group_view)

        # check eval_metric
        if isinstance(self.eval_metric, (str, list)):
            if isinstance(self.eval_metric, str):
                self.eval_metric = [self.eval_metric]
        else:
            raise TypeError('eval_metric must be str or list')
        
        for m in self.eval_metric:
            if m.lower() not in metric_name:
                raise ValueError("There is not the metric named {}!".format(m))
        self.eval_metric = [metric.lower() for metric in self.eval_metric]

        # check topk:
        if isinstance(self.topk, (int, list)):
            if isinstance(self.topk, int):
                assert self.topk > 0, 'topk must be a pistive integer or a list of postive integers'
                self.topk = list(range(1, self.topk + 1))
        else:
            raise TypeError('The topk muse be int or list')
        for number in self.topk:
            assert isinstance(number, int) and number > 0, '{} in topk is not a posttive integer'.format(number) 
        self.topk = sorted(self.topk)

    def evaluate(self, result, test_data):
        """Evaluate `model`.

        Args:
            result: TODO
            test_data: TODO

        Returns:
            str: A string consist of all results
        """
        info_str = self.evaluator.evaluate(result, test_data)
        print(info_str)

    def __str__(self):
        return 'The evaluator will evaluate test_data on {} at {}'.format(', '.join(self.eval_metric), ', '.join(map(str, self.topk)))

    def __repr__(self):
        return self.__str__()

    def __enter__(self):
        print('Evaluate Start...')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass