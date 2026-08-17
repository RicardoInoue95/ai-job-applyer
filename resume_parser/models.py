from typing import Optional
from pydantic import BaseModel, Field


class Experiencia(BaseModel):
    empresa: str
    cargo: str
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    descricao: str = ""
    tecnologias: list[str] = Field(default_factory=list)
    conquistas: list[str] = Field(default_factory=list)


class Formacao(BaseModel):
    instituicao: str
    curso: str
    data_conclusao: Optional[str] = None
    em_andamento: bool = False


class Certificacao(BaseModel):
    nome: str
    emissor: str = ""
    data: Optional[str] = None
    link: Optional[str] = None


class Idioma(BaseModel):
    nome: str
    nivel: str = ""


class ResumeJSON(BaseModel):
    nome: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    localizacao: Optional[str] = None
    resumo_profissional: Optional[str] = None
    experiencias: list[Experiencia] = Field(default_factory=list)
    formacao: list[Formacao] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)


class PerfilBase(BaseModel):
    perfil: str
    nome: str
    email: Optional[str] = None
    linkedin: Optional[str] = None
    localizacao: Optional[str] = None
    resumo_profissional: str = ""
    experiencias: list[Experiencia] = Field(default_factory=list)
    formacao: list[Formacao] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    tecnologias: list[str] = Field(default_factory=list)
