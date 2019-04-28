import json
import os
import sys
import pickle
import random
from collections import Counter

import nltk
from nltk.stem.porter import *

"""
    An iterator that filters out all relations that are not Nonexplicit relations or that do not have a second level sense type
"""
class FeatureIterator(object):
    def __init__(self, pdtb, parses):
        self.pdtb = pdtb
        self.parses = parses
        self.pos = -1
        self.spos = 0

    def ignore(self, sense, relation):
        sl_sense = self.get_second_level_sense(sense)
        return relation['Type'] != 'Implicit' or self.ignore_nonexp_relation(sl_sense)

    # Extracts the second PDTB level of a sense
    @staticmethod
    def get_second_level_sense(full_sense):
        parts = full_sense.split('.')
        return None if len(parts) <= 1 else parts[1]


    # returns true if the relation is in one of the type 2 classes that is ignored in the paper
    #       - Condition
    #       - Pragmatic Condition
    #       - Pragmatic Contrast
    #       - Pragmatic Concession
    #       - Exception
    # WARNING: This is not up-to-date anymore because CoNLL merged and moved some sense classes
    def ignore_nonexp_relation(self, sense):
        ignore = {'Condition',
                  'Pragmatic Condition',
                  'Pragmatic Contrast',
                  'Pragmatic Concession',
                  'Exception'}
        return sense == None or sense in ignore

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        self.pos += 1
        while self.pos < len(self.pdtb) and self.ignore(self.pdtb[self.pos]['Sense'][self.spos], self.pdtb[self.pos]):
            self.pos += 1
        if self.pos < len(self.pdtb):
            return self.pdtb[self.pos]
        raise StopIteration()

"""
    Abstract class that holds the PDTB and Parses data and also an iterator that can be used to browse the relations
"""
class Feature(object):
    def __init__(self, pdtb, parses):
        self.pdtb = pdtb
        self.parses = parses
        self.it = FeatureIterator(pdtb, parses)

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        raise NotImplementedError()

"""
    This iterator returns all senses of the relations that are relevant
"""
class SenseIterator(Feature):
    def __init__(self, pdtb, parses, num_pairs=500):
        super().__init__(pdtb, parses)

    def next(self):
        return FeatureIterator.get_second_level_sense(next(self.it)['Sense'][self.it.spos])

"""
    The class for the ProductionRule feature
"""
class ProductionRuleFeature(Feature):
    def __init__(self, pdtb, parses, num_rules=100):
        super().__init__(pdtb, parses)
        self.num_rules = num_rules

   # extracts all subtrees that are contained in the spans of an argument
    def extract_arg_subtrees(self, tree, tokens):
        return [st for st in tree.subtrees(filter=lambda t: set(t.leaves()).issubset(tokens))]

    # recursive function that descends a tree and returns a set of all production rules
    def eat_production_tree(self, tree):
        rules = set() 
        rule = tree.label() + ' ->'
        for n in tree:
            if not isinstance(n, str):
                if n.parent() == tree:
                    rule += ' ' + n.label()
            else:
                rule += ' ' + n
        rules.add(rule)
        return rules

    # gets all production rules as string from all subtrees in ptree which leaves are contained in tokens
    def get_production_rules(self, ptree, tokens):
        return [r for t in self.extract_arg_subtrees(ptree, tokens) for r in self.eat_production_tree(t)]

    # extracts all production rules as a set from all trees in ptrees which subtrees are contained in tokens
    def extract_productions(self, ptrees, tokens):
        prod_rules = {production for ptree in ptrees for production in self.get_production_rules(ptree, tokens)}
        return prod_rules

    def next(self):
        relation = next(self.it)

        doc = relation['DocID']

        sentence_ids_arg1 = {t[3] for t in relation['Arg1']['TokenList']}
        sentence_ids_arg2 = {t[3] for t in relation['Arg2']['TokenList']}

        token_list_arg1 = relation['Arg1']['TokenList']
        token_list_arg2 = relation['Arg2']['TokenList']
        
        tokens_arg1 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg1)
        tokens_arg2 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg2)

        parse_trees_arg1 = [nltk.ParentedTree.fromstring(self.parses[doc]['sentences'][sentence_id]['parsetree']) for sentence_id in sentence_ids_arg1]
        parse_trees_arg2 = [nltk.ParentedTree.fromstring(self.parses[doc]['sentences'][sentence_id]['parsetree']) for sentence_id in sentence_ids_arg2]

        p_arg1 = self.extract_productions(parse_trees_arg1, tokens_arg1)
        p_arg2 = self.extract_productions(parse_trees_arg2, tokens_arg2)

        return (p_arg1, p_arg2)
"""
    The class for the DependencyRule feature
"""
class DependencyRuleFeature(Feature):
    def __init__(self, pdtb, parses, num_rules=100):
        super().__init__(pdtb, parses)
        self.num_rules = num_rules
 
    # extracts dependency rules as strings from a CoNLL-style list of dependencies of a sentence
    def extract_dependencies(self, deps, tokens):
        # unpack
        deps = deps[0]
        # build dictionary mapping dependent to all labels of sourced pointing to it
        d_deps = {}
        for dep in deps:
            label = dep[0]
            dependent = dep[1].split('-')[0]
            source = dep[2].split('-')[0]
            if source in tokens and dependent in tokens:
                d = [] 
                if dependent in d_deps:
                    d = d_deps[dependent]
                d.append(label) 
                d_deps[dependent] = d
        # build set containing string representations of dependency rules
        result = set()
        for d in d_deps.keys():
            r = d + ' <-'
            for s in d_deps[d]:
                r += ' <'+s+'>'
            result.add(r)
        return result

    def next(self):
        relation = next(self.it)

        doc = relation['DocID']

        sentence_ids_arg1 = {t[3] for t in relation['Arg1']['TokenList']}
        sentence_ids_arg2 = {t[3] for t in relation['Arg2']['TokenList']}

        token_list_arg1 = relation['Arg1']['TokenList']
        token_list_arg2 = relation['Arg2']['TokenList']
        
        tokens_arg1 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg1)
        tokens_arg2 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg2)

        dependencies_arg1 = [self.parses[doc]['sentences'][sentence_id]['dependencies'] for sentence_id in sentence_ids_arg1]
        dependencies_arg2 = [self.parses[doc]['sentences'][sentence_id]['dependencies'] for sentence_id in sentence_ids_arg2]

        arg1 = self.extract_dependencies(dependencies_arg1, tokens_arg1)
        arg2 = self.extract_dependencies(dependencies_arg2, tokens_arg2)

        return (arg1, arg2)

"""
    The class for the Context feature
"""
class ContextFeature(Feature):
    def __init__(self, pdtb, parses):
        super().__init__(pdtb, parses)

    # returns true if span1 is embedded inside span2
    def is_span_embedded(self, span1, span2):
        first = True if span2[0][0] < span1[0][0] else True if span2[0][0] == span1[0][0] and span2[0][1] <= span1[0][1] else False
        last = True if span2[0][0] > span1[0][0] else True if span2[0][0] == span1[0][0] and span2[0][1] >= span1[0][1] else False
        return first and last

    # returns the spans first (sentence, word) to last (sentence, word)
    def get_span_from_tokens(self, tokenList):
        return ( (tokenList[0][3], tokenList[0][4]), (tokenList[-1][3], tokenList[-1][4]) )

    # extracts all context features from a relation
    def extract_context_features(self):
        i = self.it.pos
        # get previous, current and next relation and extract their spans
        curr = self.pdtb[i]    
        prev = self.pdtb[i-1] if i > 0 and self.pdtb[i-1]['DocID'] == curr['DocID'] else None
        nxt  = self.pdtb[i+1] if i < len(self.pdtb)-1 and self.pdtb[i+1]['DocID'] == curr['DocID'] else None

        curr_span_arg1 = self.get_span_from_tokens(curr['Arg1']['TokenList'])
        curr_span_arg2 = self.get_span_from_tokens(curr['Arg2']['TokenList'])

        prev_span_arg1 = self.get_span_from_tokens(prev['Arg1']['TokenList']) if prev else None
        prev_span_arg2 = self.get_span_from_tokens(prev['Arg2']['TokenList']) if prev else None

        next_span_arg1 = self.get_span_from_tokens(nxt['Arg1']['TokenList']) if nxt else None
        next_span_arg2 = self.get_span_from_tokens(nxt['Arg2']['TokenList']) if nxt else None

        feats = {}
        # Fully embedded argument:
        #    - prev embedded in curr.Arg1
        feats['feat1'] = self.is_span_embedded( (prev_span_arg1[0], prev_span_arg2[1]), curr_span_arg1 ) if prev else False
        #    - next embedded in curr.Arg2
        feats['feat2'] = self.is_span_embedded( (next_span_arg1[0], next_span_arg2[1]), curr_span_arg2 ) if nxt  else False
        #    - curr embedded in pref.Arg2
        feats['feat3'] = self.is_span_embedded( (curr_span_arg1[0], curr_span_arg2[1]), prev_span_arg2 ) if prev else False
        #    - curr embedded in next.Arg1
        feats['feat4'] = self.is_span_embedded( (curr_span_arg1[0], curr_span_arg2[1]), next_span_arg1 ) if nxt  else False

        # Shared arguments:
        #    - prev.Arg2 = curr.Arg1
        feats['feat5'] = prev_span_arg2 == curr_span_arg1 if prev else False
        #    - curr.Arg2 = next.Arg1
        feats['feat6'] = curr_span_arg2 == next_span_arg1 if nxt  else False

        return feats

    def next(self):
        next(self.it)
        return self.extract_context_features()

"""
    The class for the WordPair feature
"""
class WordPairFeature(Feature):
    def __init__(self, pdtb, parses, num_pairs=500):
        super().__init__(pdtb, parses)
        self.num_pairs = num_pairs
 
    # returns all stemmed wordpairs of the cartesian product between tokens_arg1 and tokens_arg2
    def extract_wordpairs(self, tokens_arg1, tokens_arg2):
        stemmer = PorterStemmer()
        stems_arg1 = {stemmer.stem(tk.lower()) for tk in tokens_arg1}
        stems_arg2 = {stemmer.stem(tk.lower()) for tk in tokens_arg2}

        return {s1+'_'+s2 for s1 in stems_arg1 for s2 in stems_arg2}

    def next(self):
        relation = next(self.it)

        doc = relation['DocID']

        token_list_arg1 = relation['Arg1']['TokenList']
        token_list_arg2 = relation['Arg2']['TokenList']
        
        tokens_arg1 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg1)
        tokens_arg2 = set(self.parses[doc]['sentences'][t[3]]['words'][t[4]][0] for t in token_list_arg2)

        return self.extract_wordpairs(tokens_arg1, tokens_arg2)


"""
    A classifier that can be trained on NonExplicit relations and predict their senses
"""
class NonExplicitSenseClassifier(object):
    def __init__(self, debug=False):
        self.model = None
        self.prod_rules = set()
        self.dep_rules = set()
        self.DEBUG = debug
    
    def get_features(self, parse_trees, deps, all_productions, all_dep_rules):
        productions = extract_productions(parse_trees)
        dep_rules = extract_dependencies(deps)

        feat = {}
        for p in all_productions:
            feat[p] = str(p in productions)
        for r in all_dep_rules:
            feat[r] = str(r in dep_rules)

        return feat

    # generates the featureset used to train a classifier
    #
    # features are: Production Rules,
    #               Dependency Rules,
    #               Wordpairs,
    #               Contextual Features
    #
    def generate_pdtb_features(self, pdtb, parses):
        extracted_productions = list(ProductionRuleFeature(pdtb, parses))
        extracted_dependency_rules = list(DependencyRuleFeature(pdtb, parses))
        extracted_context_features = list(ContextFeature(pdtb, parses))
        extracted_wordpairs = list(WordPairFeature(pdtb, parses))
        extracted_senses = list(SenseIterator(pdtb, parses))

        prod_counter = Counter(p for feature in extracted_productions for p in feature[0].union(feature[1]))
        all_productions = list(p for p, c in prod_counter.items() if c >= 5)

        dep_counter = Counter(r for feature in extracted_dependency_rules for r in feature[0].union(feature[1]))
        all_dependency_rules = list(r for r, c in dep_counter.items() if c >= 5)

        wp_counter = Counter(p for feature in extracted_wordpairs for p in feature)
        all_wordpairs = list(p for p, c in wp_counter.items() if c >= 5)

        if self.DEBUG:
            # info about the # of features. second row is # as it should be from the paper
            print('  ==> Extracted Rules')
            print('\t#Production Rules:\t', len(all_productions))
            print('\t#Dependency Rules:\t', len(all_dependency_rules))
            print('\t#Word Pairs:\t\t', len(all_wordpairs))

        feature_set = []
        for (p_arg1, p_arg2), (d_arg1, d_arg2), c_feats, word_pairs, sense in zip(extracted_productions, 
                                                                                  extracted_dependency_rules, 
                                                                                  extracted_context_features,
                                                                                  extracted_wordpairs,
                                                                                  extracted_senses):
            feat = {}
            for p in all_productions[:100]:
                feat[p + ':1' ] = str(p in p_arg1)
                feat[p + ':2' ] = str(p in p_arg2)
                feat[p + ':12'] = str(p in p_arg1 and p in p_arg2)
            for r in all_dependency_rules[:100]:
                feat[r + ':1' ] = str(r in d_arg1)
                feat[r + ':2' ] = str(r in d_arg2)
                feat[r + ':12'] = str(r in d_arg1 and r in d_arg2)
            for wp in all_wordpairs[:500]:
                feat[wp] = str(wp in word_pairs)

            feat.update(c_feats)
            feature_set.append((feat, sense))

        return all_productions, all_dependency_rules, feature_set

    # loads the model from disk
    def load(self, path):
        self.model = pickle.load(open(os.path.join(path, 'non_explicit_clf.p'), 'rb'))
        self.prod_rules = pickle.load(open(os.path.join(path, 'non_explicit_prod_rules.p'), 'rb'))
        self.dep_rules = pickle.load(open(os.path.join(path, 'non_explicit_dep_rules.p'), 'rb'))

    # save the model to disk
    def save(self, path):
        pickle.dump(self.model, open(os.path.join(path, 'non_explicit_clf.p'), 'wb'))
        pickle.dump(self.prod_rules, open(os.path.join(path, 'non_explicit_prod_rules.p'), 'wb'))
        pickle.dump(self.dep_rules, open(os.path.join(path, 'non_explicit_dep_rules.p'), 'wb'))

    def fit(self, pdtb, parses, max_iter=5):
        self.prod_rules, self.dep_rules, features = generate_pdtb_features(pdtb, parses)
        self.fit_on_features(features, max_iter=max_iter)

    def fit_on_features(self, features, max_iter=5):
        self.model = nltk.MaxentClassifier.train(features, max_iter = max_iter)

    def predict(self, X):
        pass

    def get_sense(self, sents):
        features = get_features(sents, self.prod_rules, self.dep_rules)
        return [self.model.classify(features)]

    def print_baseline(self, pdtb, parses):
        imps = list(SenseIterator(pdtb, parses))
        imp_cnt = Counter(imps)
        print('  ==> Baseline is at:', imp_cnt[imp_cnt.most_common(1)[0][0]] / len(imps))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python ' + sys.argv[0] + ' <PATH_CONLL_DIR>')
    else:
        CONLL_DIR = sys.argv[1]
        print('Loading data..')
        print('\tTraining data')
        trainpdtb = [json.loads(s) for s in open(os.path.join(CONLL_DIR, 'en.train/relations.json'), 'r').readlines()]
        trainparses = json.loads(open(os.path.join(CONLL_DIR, 'en.train/parses.json')).read())
        print('\tDevelopment data')
        devpdtb = [json.loads(s) for s in open(os.path.join(CONLL_DIR, 'en.dev/relations.json'), 'r').readlines()]
        devparses = json.loads(open(os.path.join(CONLL_DIR, 'en.dev/parses.json')).read())

        print('\tTesting data')
        testpdtb = [json.loads(s) for s in open(os.path.join(CONLL_DIR, 'en.test/relations.json'), 'r').readlines()]
        testparses = json.loads(open(os.path.join(CONLL_DIR, 'en.test/parses.json')).read())

        clf = NonExplicitSenseClassifier(debug=True)
        clf.print_baseline(testpdtb, testparses)

        all_productions, all_dep_rules, train_data = clf.generate_pdtb_features(trainpdtb, trainparses)
        #all_productions, all_dep_rules, train_data = clf.generate_pdtb_features(devpdtb, devparses)
        clf.prod_rules = all_productions
        clf.dep_rules = all_dep_rules
        clf.fit_on_features(train_data)
        print('  ==> Most informative features')
        clf.model.show_most_informative_features()
        clf.save('/tmp')
        print('....................................................................ON TRAINING DATA..................')
        print('ACCURACY {}'.format(nltk.classify.accuracy(clf.model, train_data)))

        print('....................................................................ON DEVELOPMENT DATA..................')
        _, _, val_data = clf.generate_pdtb_features(devpdtb, devparses)
        print('ACCURACY {}'.format(nltk.classify.accuracy(clf.model, val_data)))

        print('....................................................................ON TEST DATA..................')
        _, _, test_data = clf.generate_pdtb_features(testpdtb, testparses)
        print('ACCURACY {}'.format(nltk.classify.accuracy(clf.model, test_data)))
