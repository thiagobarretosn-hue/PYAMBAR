# -*- coding: utf-8 -*-
"""
Pydantic Models - PYAMBAR(lab)

Modelos de validação type-safe para dados do projeto.

Uso:
    from lib.Snippets.validation._pydantic_models import ParameterConfig, ColorScheme

    # Validar configuração de parâmetro
    param = ParameterConfig(name="Altura", is_enabled=True, group="Dimensions")

    # Validar esquema de cores
    color = ColorScheme(name="Vermelho", rgb="#FF0000", categories=["Parede"])

Author: Thiago Barreto Sobral Nunes
Version: 1.0.0
"""
try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    from typing import List, Optional, Dict, Any
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object


# ============================================================================
# PARAMETER MODELS
# ============================================================================

if PYDANTIC_AVAILABLE:
    class ParameterConfig(BaseModel):
        """
        Modelo para configuração de parâmetros.

        Attributes:
            name: Nome do parâmetro
            is_enabled: Se o parâmetro está habilitado
            group: Grupo do parâmetro (opcional)
            is_shared: Se é parâmetro compartilhado
            storage_type: Tipo de armazenamento (Text, Integer, Double, ElementId)
        """
        name: str = Field(..., min_length=1, description="Nome do parâmetro")
        is_enabled: bool = Field(default=True, description="Parâmetro habilitado")
        group: Optional[str] = Field(default=None, description="Grupo do parâmetro")
        is_shared: bool = Field(default=False, description="Parâmetro compartilhado")
        storage_type: Optional[str] = Field(default=None, description="Tipo de armazenamento")

        @field_validator('name')
        @classmethod
        def name_not_empty(cls, v):
            if not v or not v.strip():
                raise ValueError('Nome do parâmetro não pode ser vazio')
            return v.strip()

        @field_validator('storage_type')
        @classmethod
        def valid_storage_type(cls, v):
            if v is not None:
                valid_types = ['Text', 'Integer', 'Double', 'ElementId']
                if v not in valid_types:
                    raise ValueError('Tipo inválido. Deve ser um de: {}'.format(", ".join(valid_types)))
            return v

        class Config:
            str_strip_whitespace = True
            validate_assignment = True


    class ParameterConfigList(BaseModel):
        """
        Lista de configurações de parâmetros.

        Attributes:
            parameters: Lista de parâmetros
            version: Versão da configuração
        """
        parameters: List[ParameterConfig] = Field(default_factory=list)
        version: str = Field(default="1.0", description="Versão da configuração")

        @field_validator('parameters')
        @classmethod
        def no_duplicate_names(cls, v):
            names = [p.name for p in v]
            if len(names) != len(set(names)):
                raise ValueError('Nomes de parâmetros duplicados encontrados')
            return v


# ============================================================================
# COLOR MODELS
# ============================================================================

if PYDANTIC_AVAILABLE:
    class ColorScheme(BaseModel):
        """
        Modelo para esquema de cores.

        Attributes:
            name: Nome da cor/esquema
            rgb: Código RGB em formato hexadecimal (#RRGGBB)
            categories: Categorias onde aplicar
            parameter_value: Valor do parâmetro associado
        """
        name: str = Field(..., min_length=1, description="Nome do esquema")
        rgb: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$', description="Cor RGB hex")
        categories: List[str] = Field(default_factory=list, description="Categorias")
        parameter_value: Optional[str] = Field(default=None, description="Valor do parâmetro")

        @field_validator('rgb')
        @classmethod
        def validate_hex_color(cls, v):
            if not v.startswith('#'):
                v = '#' + v
            if len(v) != 7:
                raise ValueError('RGB deve estar no formato #RRGGBB')
            return v.upper()

        def to_revit_color(self):
            """
            Converte RGB hex para tupla (R, G, B) para uso no Revit.

            Returns:
                tuple: (R, G, B) valores 0-255
            """
            hex_color = self.rgb.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


    class ColorSchemeCollection(BaseModel):
        """
        Coleção de esquemas de cores.

        Attributes:
            schemes: Lista de esquemas de cores
            parameter_name: Nome do parâmetro usado
            created_at: Data de criação
        """
        schemes: List[ColorScheme] = Field(default_factory=list)
        parameter_name: str = Field(..., min_length=1)
        created_at: Optional[str] = Field(default=None)

        @field_validator('schemes')
        @classmethod
        def at_least_one_scheme(cls, v):
            if len(v) < 1:
                raise ValueError('Pelo menos um esquema de cor é necessário')
            return v


# ============================================================================
# SHEET MODELS
# ============================================================================

if PYDANTIC_AVAILABLE:
    class SheetConfig(BaseModel):
        """
        Modelo para configuração de folhas.

        Attributes:
            sheet_number: Número da folha
            sheet_name: Nome da folha
            discipline: Disciplina
            appears_in_sheet_list: Se aparece na lista de folhas
        """
        sheet_number: str = Field(..., min_length=1)
        sheet_name: str = Field(..., min_length=1)
        discipline: Optional[str] = Field(default=None)
        appears_in_sheet_list: bool = Field(default=True)

        @field_validator('sheet_number')
        @classmethod
        def valid_sheet_number(cls, v):
            if not v or not v.strip():
                raise ValueError('Número de folha não pode ser vazio')
            return v.strip()


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_parameter_config(data):
    """
    Valida dados de configuração de parâmetro.

    Args:
        data (dict): Dicionário com dados do parâmetro

    Returns:
        ParameterConfig or dict: Modelo validado ou dict original se pydantic não disponível

    Raises:
        ValueError: Se dados inválidos
    """
    if not PYDANTIC_AVAILABLE:
        # Validação básica sem pydantic
        if not data.get('name') or not data.get('name').strip():
            raise ValueError('Nome do parâmetro é obrigatório')
        return data

    return ParameterConfig(**data)


def validate_color_scheme(data):
    """
    Valida esquema de cores.

    Args:
        data (dict): Dicionário com dados do esquema

    Returns:
        ColorScheme or dict: Modelo validado ou dict original

    Raises:
        ValueError: Se dados inválidos
    """
    if not PYDANTIC_AVAILABLE:
        # Validação básica
        if not data.get('name'):
            raise ValueError('Nome é obrigatório')
        if not data.get('rgb'):
            raise ValueError('Cor RGB é obrigatória')
        return data

    return ColorScheme(**data)


def validate_json_config(json_data, model_class):
    """
    Valida dados JSON contra um modelo pydantic.

    Args:
        json_data (dict or list): Dados JSON
        model_class: Classe do modelo pydantic

    Returns:
        model instance or original data: Dados validados

    Example:
        >>> config = validate_json_config(data, ParameterConfigList)
    """
    if not PYDANTIC_AVAILABLE:
        return json_data

    try:
        return model_class(**json_data) if isinstance(json_data, dict) else model_class(json_data)
    except Exception as e:
        raise ValueError("Erro ao validar configuração: {}".format(str(e)))
