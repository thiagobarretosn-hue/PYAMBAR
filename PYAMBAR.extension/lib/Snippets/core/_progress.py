# -*- coding: utf-8 -*-
"""
Progress Bar Module - PYAMBAR(lab)

Utilitários para barras de progresso com tqdm.

Uso:
    from lib.Snippets.core._progress import progress_bar, ProgressCounter

    # Simples
    for elem in progress_bar(elements, "Processando"):
        # processar elemento
        pass

    # Com contador manual
    counter = ProgressCounter(total=100, desc="Carregando")
    for i in range(100):
        # processar
        counter.update(1)
    counter.close()

Author: Thiago Barreto Sobral Nunes
Version: 1.0.0
"""
try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


def progress_bar(iterable, desc="Processando", total=None, disable=False, **kwargs):
    """
    Cria barra de progresso para iterável.

    Args:
        iterable: Objeto iterável (lista, FilteredElementCollector, etc)
        desc (str): Descrição da operação
        total (int, optional): Total de itens (calculado automaticamente se possível)
        disable (bool): Desabilitar barra de progresso
        **kwargs: Argumentos adicionais para tqdm

    Returns:
        iterable: Iterável com ou sem barra de progresso

    Example:
        >>> walls = FilteredElementCollector(doc).OfClass(Wall).ToElements()
        >>> for wall in progress_bar(walls, "Processando paredes"):
        ...     # processar parede
        ...     pass
    """
    if disable or not TQDM_AVAILABLE:
        return iterable

    # Configurações padrão
    default_config = {
        'desc': desc,
        'unit': 'elem',
        'ncols': 80,
        'bar_format': '{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
        'colour': 'green',
    }

    # Mesclar com kwargs fornecidos (Python 2.7 compatible)
    config = default_config.copy()
    config.update(kwargs)

    # Adicionar total se fornecido
    if total is not None:
        config['total'] = total

    try:
        return _tqdm(iterable, **config)
    except Exception:
        # Fallback se tqdm falhar
        return iterable


class ProgressCounter:
    """
    Contador de progresso manual para operações complexas.

    Attributes:
        total: Total de operações
        desc: Descrição da operação

    Example:
        >>> counter = ProgressCounter(100, "Processando")
        >>> for i in range(100):
        ...     # fazer algo
        ...     counter.update(1)
        ...     counter.set_description(f"Processando item {i}")
        >>> counter.close()
    """

    def __init__(self, total, desc="Processando", disable=False, **kwargs):
        """
        Inicializa contador de progresso.

        Args:
            total (int): Total de operações
            desc (str): Descrição
            disable (bool): Desabilitar progresso
            **kwargs: Argumentos para tqdm
        """
        self.total = total
        self.desc = desc
        self.disabled = disable or not TQDM_AVAILABLE
        self._pbar = None

        if not self.disabled:
            config = {
                'total': total,
                'desc': desc,
                'unit': 'op',
                'ncols': 80,
                'bar_format': '{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
                'colour': 'cyan',
            }
            config.update(kwargs)
            try:
                self._pbar = _tqdm(**config)
            except Exception:
                self.disabled = True

    def update(self, n=1):
        """Atualiza progresso."""
        if not self.disabled and self._pbar:
            self._pbar.update(n)

    def set_description(self, desc):
        """Atualiza descrição."""
        if not self.disabled and self._pbar:
            self._pbar.set_description(desc)

    def set_postfix(self, **kwargs):
        """Define informações adicionais."""
        if not self.disabled and self._pbar:
            self._pbar.set_postfix(**kwargs)

    def close(self):
        """Fecha barra de progresso."""
        if not self.disabled and self._pbar:
            self._pbar.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def batch_progress(iterable, batch_size, desc="Processando lotes", **kwargs):
    """
    Cria barra de progresso para processamento em lotes.

    Args:
        iterable: Iterável para processar
        batch_size (int): Tamanho do lote
        desc (str): Descrição
        **kwargs: Argumentos para tqdm

    Yields:
        list: Lote de itens

    Example:
        >>> elements = list(range(1000))
        >>> for batch in batch_progress(elements, batch_size=100, desc="Lotes"):
        ...     # processar lote
        ...     process_batch(batch)
    """
    items = list(iterable)
    total_batches = (len(items) + batch_size - 1) // batch_size

    pbar_iterable = range(0, len(items), batch_size)

    if TQDM_AVAILABLE:
        pbar_iterable = _tqdm(
            pbar_iterable,
            total=total_batches,
            desc=desc,
            unit='lote',
            **kwargs
        )

    for i in pbar_iterable:
        yield items[i:i + batch_size]


class MultiProgress:
    """
    Gerenciador para múltiplas barras de progresso.

    Example:
        >>> mp = MultiProgress()
        >>> pbar1 = mp.add_bar(100, "Tarefa 1")
        >>> pbar2 = mp.add_bar(50, "Tarefa 2")
        >>>
        >>> for i in range(100):
        ...     pbar1.update(1)
        >>>
        >>> for i in range(50):
        ...     pbar2.update(1)
        >>>
        >>> mp.close_all()
    """

    def __init__(self):
        """Inicializa gerenciador."""
        self.bars = []
        self.disabled = not TQDM_AVAILABLE

    def add_bar(self, total, desc="Processando", position=None, **kwargs):
        """
        Adiciona nova barra de progresso.

        Args:
            total (int): Total de itens
            desc (str): Descrição
            position (int, optional): Posição da barra
            **kwargs: Argumentos para tqdm

        Returns:
            ProgressCounter: Contador de progresso
        """
        if position is None:
            position = len(self.bars)

        counter = ProgressCounter(
            total=total,
            desc=desc,
            position=position,
            leave=True,
            **kwargs
        )
        self.bars.append(counter)
        return counter

    def close_all(self):
        """Fecha todas as barras."""
        for bar in self.bars:
            bar.close()
        self.bars = []


# Funções de conveniência
def simple_progress(items, description="Processando"):
    """
    Wrapper simples para progresso.

    Args:
        items: Lista de itens
        description: Descrição da operação

    Returns:
        iterable com progresso
    """
    return progress_bar(items, desc=description)


def disabled_progress(iterable):
    """
    Retorna iterável sem barra de progresso.

    Útil para manter código consistente quando progresso não é desejado.
    """
    return iterable
